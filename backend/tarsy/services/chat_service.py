"""
Chat Service for managing follow-up chat conversations.

This service orchestrates chat lifecycle and message processing, following the same
patterns as AlertService for consistency and reliability.
"""

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from tarsy.agents.prompts.builders import ChatExchange

from tarsy.config.settings import get_settings
from tarsy.hooks.hook_context import stage_execution_context
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.alert import ProcessingAlert
from tarsy.models.constants import StageStatus
from tarsy.models.db_models import Chat, ChatUserMessage, StageExecution
from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
from tarsy.models.processing_context import (
    ChainContext,
    ChatMessageContext,
    SessionContextData,
)
from tarsy.models.unified_interactions import LLMInteraction
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.history_service import HistoryService
from tarsy.services.mcp_client_factory import MCPClientFactory
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

logger = get_module_logger(__name__)


class ChatService:
    """
    Service for managing follow-up chat conversations.
    
    Architecture:
    - Orchestrates chat lifecycle and message processing
    - Delegates ALL database operations to HistoryService
    - Never directly accesses repositories (proper service layering)
    - Coordinates between HistoryService, AgentFactory, and MCP systems
    
    Patterns:
    - Mirrors AlertService for consistency (pod tracking, timeouts, MCP cleanup)
    - Uses stage_execution_context for event publishing
    - Maintains proper service → service → repository layering
    """
    
    def __init__(
        self,
        history_service: HistoryService,
        agent_factory: AgentFactory,
        mcp_client_factory: MCPClientFactory
    ):
        """
        Initialize ChatService with dependencies.
        
        Args:
            history_service: Service for all database operations
            agent_factory: Factory for creating ChatAgent instances
            mcp_client_factory: Factory for creating session-scoped MCP clients
        """
        self.history_service = history_service
        self.agent_factory = agent_factory
        self.mcp_client_factory = mcp_client_factory
        self.settings = get_settings()
    
    async def create_chat(
        self,
        session_id: str,
        created_by: str
    ) -> Chat:
        """
        Create a new chat for a terminated session.
        
        Steps:
        1. Validate session exists and is in terminal state (completed, failed, or cancelled)
        2. Check if chat already exists
        3. Validate chain has chat_enabled=true
        4. Capture session context (using _capture_session_context)
        5. Determine MCP servers (chain config + session custom)
        6. Create Chat record with initial_context
        
        Args:
            session_id: Session identifier to create chat for
            created_by: User creating the chat
            
        Returns:
            Created Chat object
            
        Raises:
            ValueError: If session not found, not in terminal state, or chat disabled
        """
        # Get session and validate (wrap synchronous call in to_thread to avoid blocking)
        session = await asyncio.to_thread(self.history_service.get_session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Import terminal statuses from constants
        from tarsy.models.constants import AlertSessionStatus
        
        # Check if session is in a terminal state (completed, failed, or cancelled)
        terminal_statuses = AlertSessionStatus.terminal_values()
        if session.status not in terminal_statuses:
            raise ValueError(
                f"Can only create chat for terminated sessions. "
                f"Current status: {session.status}, terminal statuses: {', '.join(terminal_statuses)}"
            )
        
        # Check if chat already exists (via history_service)
        existing_chat = await self.history_service.get_chat_by_session(session_id)
        if existing_chat:
            logger.info(f"Chat already exists for session {session_id}")
            return existing_chat
        
        # Validate chain has chat enabled
        chain_config = session.chain_config
        if chain_config and not chain_config.chat_enabled:
            raise ValueError(
                f"Chat is disabled for chain '{chain_config.chain_id}'. "
                f"Set chat_enabled=true in agents.yaml to enable chat for this chain."
            )
        
        # Capture session context from LLM interactions (returns typed dataclass)
        context = await self._capture_session_context(session_id)
        
        # Determine MCP selection for chat
        # This captures which servers/tools were used in the original session
        mcp_selection = self._determine_mcp_selection_from_session(session)
        
        # Create chat record with typed fields (type-safe!)
        chat = Chat(
            session_id=session_id,
            created_by=created_by,
            conversation_history=context.conversation_history,
            chain_id=context.chain_id,
            mcp_selection=mcp_selection.model_dump() if mcp_selection else None,
            context_captured_at_us=context.captured_at_us
        )
        
        created_chat = await self.history_service.create_chat(chat)
        logger.info(f"Created chat {created_chat.chat_id} for session {session_id}")
        
        # Publish chat created event
        from tarsy.services.events.event_helpers import publish_chat_created
        await publish_chat_created(
            session_id=session_id,
            chat_id=created_chat.chat_id,
            created_by=created_by
        )
        
        return created_chat
    
    async def _start_interaction_recording_task(
        self,
        chat_id: str,
        session_id: str
    ) -> asyncio.Task:
        """
        Start background task to record interactions during processing.
        
        This task periodically updates both session and chat last_interaction_at
        timestamps to keep them marked as active for orphan detection.
        
        Args:
            chat_id: Chat identifier
            session_id: Parent session identifier
            
        Returns:
            Async task that can be cancelled
        """
        async def record_interactions():
            while True:
                try:
                    await asyncio.sleep(5)  # Record every 5 seconds
                    # Record both session and chat interactions
                    if self.history_service:
                        # Update parent session timestamp (existing behavior)
                        if hasattr(self.history_service, "record_session_interaction"):
                            rec = self.history_service.record_session_interaction
                            if asyncio.iscoroutinefunction(rec):
                                await rec(session_id)
                            else:
                                await asyncio.to_thread(rec, session_id)
                        
                        # Update chat timestamp (keeps processing marker fresh)
                        if hasattr(self.history_service, "record_chat_interaction"):
                            rec_chat = self.history_service.record_chat_interaction
                            if asyncio.iscoroutinefunction(rec_chat):
                                await rec_chat(chat_id)
                            else:
                                await asyncio.to_thread(rec_chat, chat_id)
                except asyncio.CancelledError:
                    logger.debug(f"Interaction recording task cancelled for chat {chat_id}")
                    break
                except Exception as e:
                    logger.debug(f"Error recording interactions for chat {chat_id}: {e}")
        
        return asyncio.create_task(record_interactions())
    
    async def create_user_message_and_start_processing(
        self,
        chat_id: str,
        user_question: str,
        author: str,
        stage_execution_id: str
    ) -> tuple[str, str]:
        """
        Create user message record and return IDs for immediate response.
        
        This method creates the ChatUserMessage synchronously and returns both
        the database message_id and stage_execution_id for the controller to
        include in the immediate response. The actual processing is then started
        as a background task.
        
        Args:
            chat_id: Chat identifier
            user_question: User's follow-up question
            author: User sending the message
            stage_execution_id: Pre-generated stage execution ID (for consistent tracking)
            
        Returns:
            Tuple of (message_id, stage_execution_id) for immediate response
            
        Raises:
            ValueError: If chat not found or validation fails
        """
        # 1. Get chat and validate (via history_service)
        chat = await self.history_service.get_chat_by_id(chat_id)
        if not chat:
            raise ValueError(f"Chat {chat_id} not found")
        
        # 2. Create user message record (via history_service)
        user_msg = ChatUserMessage(
            chat_id=chat_id,
            content=user_question,
            author=author
        )
        await self.history_service.create_chat_user_message(user_msg)
        logger.info(f"Created chat message {user_msg.message_id} for chat {chat_id}")
        
        # Publish user message event
        from tarsy.services.events.event_helpers import publish_chat_user_message
        await publish_chat_user_message(
            session_id=chat.session_id,
            chat_id=chat_id,
            message_id=user_msg.message_id,
            content=user_question,
            author=author
        )
        
        return (user_msg.message_id, stage_execution_id)
    
    async def process_chat_message(
        self,
        chat_id: str,
        user_question: str,
        author: str,
        stage_execution_id: str,
        message_id: str
    ) -> str:
        """
        Process a user chat message and generate assistant response.
        
        This is the main processing method called from background tasks.
        Matches AlertService.process_alert() pattern.
        
        Follows the same patterns as AlertService.process_alert() for consistency:
        - Pod ownership tracking (graceful shutdown support)
        - Session interaction recording (orphan detection)
        - Chat interaction recording (keeps processing marker fresh)
        - Timeout handling (600s like sessions)
        - MCP client cleanup in finally block
        - Stage execution lifecycle management
        - Event publishing via stage execution hooks (reuses existing events)
        
        Args:
            chat_id: Chat identifier
            user_question: User's follow-up question
            author: User sending the message
            stage_execution_id: Pre-generated stage execution ID (for consistent tracking)
            message_id: Database message ID from ChatUserMessage record
            
        Returns:
            Stage execution ID for this chat response
            
        Raises:
            ValueError: If chat not found or validation fails
            asyncio.TimeoutError: If execution exceeds timeout
            Exception: Other processing errors
        """
        chat_mcp_client = None
        execution_id = stage_execution_id  # Use provided ID instead of generating
        interaction_recording_task = None
        
        try:
            # 1. Get chat (already validated in create_user_message_and_start_processing)
            chat = await self.history_service.get_chat_by_id(chat_id)
            if not chat:
                raise ValueError(f"Chat {chat_id} not found")
            
            # 2. User message already created in create_user_message_and_start_processing
            # Just use the provided message_id
            
            # 3. Build context (initial context OR cumulative from last execution)
            message_context = await self._build_message_context(chat, user_question)
            
            # 4. Create stage execution for this response
            # Uses stage execution context manager (like AlertService)
            # Use the provided execution_id for consistent tracking
            stage_execution = StageExecution(
                execution_id=execution_id,  # Use pre-generated ID from controller
                session_id=chat.session_id,
                stage_id=f"chat-response-{message_id}",
                stage_index=0,  # Chat messages don't have meaningful stage index
                stage_name="Chat Response",
                agent="ChatAgent",
                status=StageStatus.PENDING.value,
                chat_id=chat_id,
                chat_user_message_id=message_id
            )
            
            # Trigger stage execution hooks (creates DB record, publishes events)
            async with stage_execution_context(stage_execution):
                pass
            
            logger.info(f"Created chat message execution {execution_id} for chat {chat_id}")
            
            # 5. Track pod ownership for graceful shutdown (mirrors AlertService)
            from tarsy.main import get_pod_id
            pod_id = get_pod_id()
            
            if pod_id == "unknown":
                logger.warning(
                    "TARSY_POD_ID not set - chat messages from multiple pods may not gracefully shutdown"
                )
            
            # Start chat message processing tracking (sets pod_id and last_interaction_at)
            if self.history_service:
                await self.history_service.start_chat_message_processing(chat_id, pod_id)
            
            logger.debug(f"Chat message {execution_id} being processed by pod {pod_id}")
            
            # 6. Record interaction timestamps for orphan detection
            # Both session (parent) and chat need their timestamps updated
            if self.history_service:
                # Update parent session timestamp
                if hasattr(self.history_service, "record_session_interaction"):
                    rec = self.history_service.record_session_interaction
                    if asyncio.iscoroutinefunction(rec):
                        await rec(chat.session_id)
                    else:
                        await asyncio.to_thread(rec, chat.session_id)
                
                # Update chat timestamp (keeps processing marker fresh)
                if hasattr(self.history_service, "record_chat_interaction"):
                    rec_chat = self.history_service.record_chat_interaction
                    if asyncio.iscoroutinefunction(rec_chat):
                        await rec_chat(chat_id)
                    else:
                        await asyncio.to_thread(rec_chat, chat_id)
            
            # Start background task to keep interaction timestamps fresh during processing
            interaction_recording_task = await self._start_interaction_recording_task(
                chat_id=chat_id,
                session_id=chat.session_id
            )
            logger.debug(f"Started interaction recording task for chat {chat_id}")
            
            # 7. Update stage execution to started
            await self._update_stage_execution_started(execution_id)
            
            # 8. Get MCP selection from chat
            mcp_selection = (
                MCPSelectionConfig(**chat.mcp_selection) 
                if chat.mcp_selection 
                else None
            )
            
            # 9. Determine iteration strategy and LLM provider from parent session's chain config
            session = await asyncio.to_thread(self.history_service.get_session, chat.session_id)
            iteration_strategy = self._determine_iteration_strategy_from_session(session) if session else None
            llm_provider = self._determine_llm_provider_from_session(session) if session else None
            
            # 10. Create session-scoped MCP client for this chat execution
            logger.info(f"Creating MCP client for chat message {execution_id}")
            chat_mcp_client = await self.mcp_client_factory.create_client()
            
            # 11. Create ChatAgent with iteration strategy and LLM provider from parent session
            chat_agent = self.agent_factory.get_agent(
                agent_identifier="ChatAgent",
                mcp_client=chat_mcp_client,
                iteration_strategy=iteration_strategy,
                llm_provider=llm_provider
            )
            
            # Set stage execution ID for interaction tagging
            chat_agent.set_current_stage_execution_id(execution_id)
            
            # Set chat ID for interaction recording in hooks
            chat_agent.set_current_chat_id(chat_id)
            
            # 11. Build ChainContext for chat (minimal, for compatibility)
            from tarsy.utils.timestamp import now_us
            processing_alert = ProcessingAlert(
                alert_type="chat",  # Special type for chat
                severity="info",  # Chat messages are informational
                timestamp=now_us(),  # Current timestamp
                alert_data={"chat_id": chat_id, "user_question": user_question},
                mcp=mcp_selection  # Pass MCP selection
            )
            
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id=chat.session_id,
                current_stage_name="chat-response",
                author=author
            )
            
            # Add chat-specific context to chain_context (type-safe!)
            chain_context.chat_context = message_context  # ChatMessageContext dataclass
            
            # 12. Execute ChatAgent with timeout (600s like sessions)
            try:
                result = await asyncio.wait_for(
                    chat_agent.process_alert(chain_context),
                    timeout=self.settings.alert_processing_timeout
                )
                
                # 13. Update stage execution as completed
                await self._update_stage_execution_completed(execution_id, result)
                
                logger.info(f"Chat message {execution_id} completed successfully")
                return execution_id
                
            except asyncio.TimeoutError:
                error_msg = f"Chat message processing exceeded {self.settings.alert_processing_timeout}s timeout"
                logger.error(f"{error_msg} for execution {execution_id}")
                await self._update_stage_execution_failed(execution_id, error_msg)
                raise
            
        except Exception as e:
            error_msg = f"Chat message processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Update stage execution as failed if we have execution_id
            if execution_id:
                await self._update_stage_execution_failed(execution_id, str(e))
            
            raise
        
        finally:
            # Cancel interaction recording task
            if interaction_recording_task and not interaction_recording_task.done():
                interaction_recording_task.cancel()
                with suppress(asyncio.CancelledError):
                    await interaction_recording_task
                logger.debug(f"Cancelled interaction recording task for chat {chat_id}")
            
            # CRITICAL: Always cleanup MCP client (like AlertService)
            if chat_mcp_client:
                try:
                    logger.debug(f"Closing MCP client for chat message {execution_id}")
                    await chat_mcp_client.close()
                    logger.debug(f"MCP client closed for chat message {execution_id}")
                except Exception as cleanup_error:
                    logger.warning(f"Error closing chat MCP client: {cleanup_error}")
    
    # Context Building Helpers
    # 
    # These methods handle extracting and formatting conversation history
    # for chat messages. The design eliminates duplication by using a
    # common helper for both initial chat creation and subsequent messages.
    #
    # Flow:
    # 1. create_chat() → _capture_session_context() 
    #                   → _get_formatted_conversation_from_llm_interactions()
    #                   → Stores formatted text in chat.conversation_history
    #
    # 2. send_message() → _build_message_context()
    #    First message:  → Returns chat.conversation_history (pre-formatted)
    #    Later messages: → _get_formatted_conversation_from_llm_interactions()
    #                    → Formats conversation from last chat execution
    
    async def _get_formatted_conversation_from_llm_interactions(
        self,
        llm_interactions: List[LLMInteraction]
    ) -> str:
        """
        Extract and format conversation history from LLM interactions.
        
        Takes the LAST interaction (which contains complete cumulative history)
        and formats it as readable text for the chat agent using PromptBuilder.
        
        This is the core helper used by both:
        - create_chat(): Gets conversation from session's LLM interactions
        - send_message(): Gets conversation from previous chat execution's LLM interactions
        
        Args:
            llm_interactions: List of LLM interactions (ordered by timestamp)
        
        Returns:
            Formatted conversation history as text
        """
        if not llm_interactions:
            raise ValueError("No LLM interactions provided for formatting")
        
        # Find the last interaction with a valid conversation suitable for chat context
        # - Exclude interactions with None conversation (cancelled/failed)
        # - Only include interaction types suitable for chat context (see CHAT_CONTEXT_INTERACTION_TYPES)
        from tarsy.models.constants import CHAT_CONTEXT_INTERACTION_TYPES
        
        last_valid_interaction = None
        for interaction in reversed(llm_interactions):
            if (interaction.conversation is not None and 
                interaction.interaction_type in CHAT_CONTEXT_INTERACTION_TYPES):
                last_valid_interaction = interaction
                break
        
        # If no valid interaction found, return cancellation message
        if last_valid_interaction is None:
            return "[Investigation was cancelled before completion]"
        
        # Use PromptBuilder to format investigation context
        from tarsy.agents.prompts.builders import PromptBuilder
        prompt_builder = PromptBuilder()
        
        return prompt_builder.format_investigation_context(last_valid_interaction.conversation)
    
    async def _capture_session_context(self, session_id: str) -> SessionContextData:
        """
        Capture session context for initial chat creation.
        
        Gets the complete investigation history from the session's
        LLM interactions and formats it for chat use.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionContextData with conversation_history, chain_id, and timestamp
        """
        # Get session's LLM interactions
        llm_interactions = await self.history_service.get_llm_interactions_for_session(
            session_id
        )
        
        if not llm_interactions:
            raise ValueError(f"No LLM interactions found for session {session_id}")
        
        # Format conversation using common helper
        history_text = await self._get_formatted_conversation_from_llm_interactions(
            llm_interactions
        )
        
        # Get session for metadata (wrap synchronous call in to_thread to avoid blocking)
        session = await asyncio.to_thread(self.history_service.get_session, session_id)
        
        # Return typed dataclass
        return SessionContextData(
            conversation_history=history_text,
            chain_id=session.chain_id,
            captured_at_us=now_us()
        )
    
    def _determine_mcp_selection_from_session(
        self,
        session
    ) -> Optional[MCPSelectionConfig]:
        """
        Capture the MCP configuration that was actually used during the session.
        
        This ensures chat has access to the SAME servers/tools as the original
        investigation, regardless of whether they came from:
        - Custom MCP selection provided in the alert request, OR
        - Default MCP servers defined in agents.yaml for the chain/stages
        
        Strategy:
        1. If session.mcp_selection exists (alert had custom MCP selection):
           → Use that (preserves server names + any tool filtering)
           
        2. Otherwise (session used default agent servers):
           → Extract default servers from chain_definition.stages
           → Look up each agent's default mcp_servers from configuration
           → Build MCPSelectionConfig from those defaults (no tool filtering)
        
        Args:
            session: AlertSession object
            
        Returns:
            MCPSelectionConfig with the servers/tools used during the session,
            or None if no MCP servers were used (shouldn't happen in practice)
        """
        # Case 1: Session had custom MCP selection from alert request
        if session.mcp_selection:
            logger.info(f"Chat using custom MCP selection from session {session.session_id}")
            return MCPSelectionConfig(**session.mcp_selection)
        
        # Case 2: Session used default agent servers - reconstruct them
        chain_config = session.chain_config
        if not chain_config:
            logger.warning(f"No chain definition in session {session.session_id}")
            return None
        
        # Extract unique server names from all stages' default configurations
        server_names = set()
        
        for stage in chain_config.stages:
            agent_name = stage.agent
            if not agent_name:
                continue
            
            # Look up agent's default MCP servers from configuration
            # Try configured agents first, then builtin agents
            if self.agent_factory.agent_configs and agent_name in self.agent_factory.agent_configs:
                agent_config = self.agent_factory.agent_configs[agent_name]
                server_names.update(agent_config.mcp_servers)
            else:
                # Builtin agent - get MCP servers by calling the classmethod
                try:
                    # Get the agent class from the factory's registry
                    agent_class = self.agent_factory.static_agent_classes.get(agent_name)
                    if agent_class:
                        # Call mcp_servers() as a classmethod (no instantiation needed)
                        if hasattr(agent_class, 'mcp_servers'):
                            mcp_server_list = agent_class.mcp_servers()
                            if mcp_server_list:  # Guard against None
                                server_names.update(mcp_server_list)
                                logger.debug(f"Got MCP servers from builtin agent {agent_name}: {mcp_server_list}")
                except Exception as e:
                    logger.warning(f"Failed to get MCP servers from builtin agent '{agent_name}': {e}")
        
        if not server_names:
            logger.warning(f"No MCP servers found in chain definition for session {session.session_id}")
            return None
        
        logger.info(f"Chat using default servers from chain: {sorted(server_names)}")
        
        # Build MCPSelectionConfig from collected default servers (no tool filtering)
        return MCPSelectionConfig(
            servers=[
                MCPServerSelection(name=server_name, tools=None)
                for server_name in sorted(server_names)
            ]
        )
    
    def _determine_iteration_strategy_from_session(
        self,
        session
    ) -> Optional[str]:
        """
        Determine the iteration strategy to use for chat based on the session's chain config.
        
        Uses the last stage's iteration strategy from the chain configuration,
        ensuring chat uses the same strategy as the final investigation stage.
        
        Strategy resolution:
        1. Get the last stage from the chain configuration
        2. If stage has explicit iteration_strategy, use that
        3. Otherwise, look up the agent's default strategy from configuration
        4. Fall back to None (ChatAgent will use its default - REACT)
        
        Args:
            session: AlertSession object with chain_config
            
        Returns:
            Iteration strategy string (e.g., "react", "native-thinking") or None
        """
        chain_config = session.chain_config
        if not chain_config or not chain_config.stages:
            logger.debug(f"No chain config or stages for session {session.session_id}, using default strategy")
            return None
        
        # Use the last stage's strategy (most relevant for chat follow-up)
        last_stage = chain_config.stages[-1]
        
        # Check if stage has explicit strategy override
        if last_stage.iteration_strategy:
            logger.info(f"Chat using explicit stage strategy: {last_stage.iteration_strategy}")
            return last_stage.iteration_strategy
        
        # Otherwise, look up agent's default strategy
        agent_name = last_stage.agent
        if not agent_name:
            return None
        
        # Try configured agents first
        if self.agent_factory.agent_configs and agent_name in self.agent_factory.agent_configs:
            agent_config = self.agent_factory.agent_configs[agent_name]
            strategy = agent_config.iteration_strategy
            if strategy:
                logger.info(f"Chat using configured agent '{agent_name}' default strategy: {strategy.value}")
                return strategy.value
        
        # Try builtin agents
        from tarsy.config.builtin_config import get_builtin_agent_config
        try:
            builtin_config = get_builtin_agent_config(agent_name)
            strategy = builtin_config.get("iteration_strategy")
            if strategy:
                logger.info(f"Chat using builtin agent '{agent_name}' default strategy: {strategy}")
                return strategy
        except ValueError:
            pass  # Not a builtin agent
        
        logger.debug(f"No strategy found for agent '{agent_name}', using ChatAgent default")
        return None
    
    def _determine_llm_provider_from_session(
        self,
        session
    ) -> Optional[str]:
        """
        Determine the LLM provider to use for chat based on the session's chain config.
        
        Uses the chain-level provider from the chain configuration. If no chain-level
        provider is defined, returns None to use the global default.
        
        Args:
            session: AlertSession object with chain_config
            
        Returns:
            LLM provider name string or None for global default
        """
        chain_config = session.chain_config
        if not chain_config:
            logger.debug(f"No chain config for session {session.session_id}, using default LLM provider")
            return None
        
        # Use chain-level provider for chat (consistent with executive summary)
        if chain_config.llm_provider:
            logger.info(f"Chat using chain-level LLM provider: {chain_config.llm_provider}")
            return chain_config.llm_provider
        
        logger.debug(f"No chain-level LLM provider for session {session.session_id}, using global default")
        return None
    
    async def _build_chat_exchanges(
        self,
        chat_id: str
    ) -> List['ChatExchange']:
        """
        Build structured chat exchange data from DB records.
        
        Queries ChatUserMessage and corresponding LLMInteractions,
        returns structured data for PromptBuilder to format.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            List of ChatExchange objects (ordered chronologically)
        """
        from tarsy.agents.prompts.builders import ChatExchange
        
        # Query ChatUserMessage records for chat_id (ordered by created_at_us)
        user_messages = await self.history_service.get_chat_user_messages(
            chat_id=chat_id, 
            limit=100,  # Reasonable limit
            offset=0
        )
        
        # Query stage executions once and map by chat_user_message_id
        # This avoids repeated DB calls and fixes issues with None started_at_us timestamps
        chat_executions = await self.history_service.get_stage_executions_for_chat(chat_id)
        execution_map = {
            exec.chat_user_message_id: exec 
            for exec in chat_executions 
            if exec.chat_user_message_id
        }
        
        exchanges = []
        for msg in user_messages:
            # Look up the stage execution using the message ID
            matching_execution = execution_map.get(msg.message_id)
            
            if not matching_execution:
                logger.warning(f"No matching execution found for chat message {msg.message_id}")
                continue
            
            # Get LLM interactions for this execution
            llm_interactions = await self.history_service.get_llm_interactions_for_stage(
                matching_execution.execution_id
            )
            
            if not llm_interactions:
                logger.warning(f"No LLM interactions found for execution {matching_execution.execution_id}")
                continue
            
            # Get the last interaction which has the complete conversation
            last_interaction = llm_interactions[-1]
            
            # Skip if conversation is None (e.g., cancelled execution with no data)
            if last_interaction.conversation is None:
                logger.warning(f"Skipping chat exchange for message {msg.message_id} - conversation is None")
                continue
            
            # Build ChatExchange object
            exchanges.append(ChatExchange(
                user_question=msg.content,
                conversation=last_interaction.conversation
            ))
        
        return exchanges
    
    async def _build_message_context(
        self,
        chat: Chat,
        user_question: str
    ) -> ChatMessageContext:
        """
        Build context for new chat message including conversation history.
        
        Strategy for context accumulation:
        - First chat message: Use chat.conversation_history (original investigation only)
        - Subsequent messages: Combine chat.conversation_history (original investigation)
          with formatted chat history (all previous Q&A exchanges)
        
        This approach keeps the original investigation clean and separate from chat history,
        avoiding nested formatting issues.
        
        Args:
            chat: Chat object
            user_question: User's follow-up question
            
        Returns:
            ChatMessageContext with conversation_history, user_question, and chat_id
        """
        # Get previous chat executions for this chat
        prev_executions = await self._get_chat_executions(chat.chat_id)
        
        if not prev_executions:
            # First chat message - use pre-formatted context from session
            # (Already formatted during create_chat() with investigation only)
            context_history = chat.conversation_history
        else:
            # Subsequent message - build structured exchanges from DB
            exchanges = await self._build_chat_exchanges(chat.chat_id)
            
            # Format chat history using PromptBuilder
            from tarsy.agents.prompts.builders import PromptBuilder
            prompt_builder = PromptBuilder()
            
            chat_history_formatted = prompt_builder.format_chat_history(exchanges)
            
            # Combine original investigation with chat history
            context_history = chat.conversation_history + chat_history_formatted
        
        # Return typed dataclass (type-safe!)
        return ChatMessageContext(
            conversation_history=context_history,
            user_question=user_question,
            chat_id=chat.chat_id
        )
    
    async def _get_chat_executions(self, chat_id: str) -> List[StageExecution]:
        """
        Get all stage executions for a chat, ordered by timestamp.
        
        Note: Delegates to HistoryService - services never access repositories directly.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            List of StageExecution records for this chat
        """
        return await self.history_service.get_stage_executions_for_chat(chat_id)
    
    # Stage Execution Lifecycle Methods (similar to AlertService)
    
    async def _update_stage_execution_started(self, stage_execution_id: str):
        """
        Update stage execution as started.
        
        Similar to AlertService._update_stage_execution_started()
        
        Args:
            stage_execution_id: Stage execution identifier
        """
        try:
            if not self.history_service:
                return
            
            # Get existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update to active status and set start time
            existing_stage.status = StageStatus.ACTIVE.value
            existing_stage.started_at_us = now_us()
            
            # Trigger stage execution hooks (updates DB + broadcasts to dashboard)
            async with stage_execution_context(existing_stage):
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as started")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as started: {str(e)}")
    
    async def _update_stage_execution_completed(
        self, 
        stage_execution_id: str, 
        result: AgentExecutionResult
    ):
        """
        Update stage execution as completed.
        
        Similar to AlertService._update_stage_execution_completed()
        
        Args:
            stage_execution_id: Stage execution identifier
            result: Agent execution result
        """
        try:
            if not self.history_service:
                return
            
            # Get existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update completion fields
            existing_stage.status = result.status.value
            existing_stage.completed_at_us = result.timestamp_us
            existing_stage.stage_output = result.model_dump(mode='json')
            existing_stage.error_message = None
            
            # Calculate duration
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int(
                    (existing_stage.completed_at_us - existing_stage.started_at_us) / 1000
                )
            
            # Trigger stage execution hooks (updates DB + broadcasts to dashboard)
            async with stage_execution_context(existing_stage):
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as completed")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as completed: {str(e)}")
    
    async def _update_stage_execution_failed(self, stage_execution_id: str, error_message: str):
        """
        Update stage execution as failed.
        
        Similar to AlertService._update_stage_execution_failed()
        
        Args:
            stage_execution_id: Stage execution identifier
            error_message: Error description
        """
        try:
            if not self.history_service:
                return
            
            # Get existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update failure fields
            existing_stage.status = StageStatus.FAILED.value
            existing_stage.completed_at_us = now_us()
            existing_stage.stage_output = None
            existing_stage.error_message = error_message
            
            # Calculate duration
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int(
                    (existing_stage.completed_at_us - existing_stage.started_at_us) / 1000
                )
            
            # Trigger stage execution hooks (updates DB + broadcasts to dashboard)
            async with stage_execution_context(existing_stage):
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as failed")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as failed: {str(e)}")


# ===== Service Factory for Dependency Injection =====

# Global chat service instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """
    Dependency injection function for FastAPI endpoints.
    
    Returns:
        Initialized ChatService instance
        
    Raises:
        HTTPException: If service not initialized
    """
    from fastapi import HTTPException
    
    if _chat_service is None:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    return _chat_service


def initialize_chat_service(
    history_service: HistoryService,
    agent_factory: AgentFactory,
    mcp_client_factory: MCPClientFactory,
) -> ChatService:
    """
    Initialize global chat service instance.
    
    Args:
        history_service: History service for database operations
        agent_factory: Agent factory for creating ChatAgent
        mcp_client_factory: MCP client factory for creating session-scoped MCP clients
        
    Returns:
        Initialized ChatService instance
    """
    global _chat_service
    _chat_service = ChatService(
        history_service=history_service,
        agent_factory=agent_factory,
        mcp_client_factory=mcp_client_factory,
    )
    logger.info("Chat service initialized")
    return _chat_service
