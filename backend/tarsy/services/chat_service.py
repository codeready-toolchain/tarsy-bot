"""
Chat Service for managing follow-up chat conversations.

This service orchestrates chat lifecycle and message processing, following the same
patterns as AlertService for consistency and reliability.
"""

import asyncio
from typing import List, Optional

from tarsy.config.settings import get_settings
from tarsy.hooks.hook_context import stage_execution_context
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.alert import ProcessingAlert
from tarsy.models.constants import StageStatus
from tarsy.models.db_models import Chat, ChatUserMessage, StageExecution
from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
from tarsy.models.processing_context import ChainContext, ChatMessageContext, SessionContextData
from tarsy.models.unified_interactions import LLMConversation, LLMInteraction
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.history_service import HistoryService
from tarsy.services.mcp_client_factory import MCPClientFactory
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

logger = get_module_logger(__name__)


def format_conversation_history_as_text(conversation: LLMConversation) -> str:
    """
    Format LLM conversation as readable investigation history.
    
    Extracts user/assistant messages (skips system instructions) and formats
    with clear section markers to distinguish historical context from current
    chat instructions.
    
    The formatted history includes:
    - Initial investigation request (alert data, runbook, available tools)
    - All ReAct reasoning (Thought/Action cycles)
    - Tool observations (results)
    - Final analysis
    
    Args:
        conversation: LLMConversation from LLMInteraction.conversation field
        
    Returns:
        Formatted string with clear section markers
        
    Note: The tools list from the original investigation is preserved as context.
    This shows what tools were available during the investigation. The ChatAgent
    will receive its own current tools list in the system message.
    """
    from tarsy.models.llm_models import MessageRole
    
    sections = []
    sections.append("=" * 80)
    sections.append("ORIGINAL ALERT INVESTIGATION HISTORY")
    sections.append("=" * 80)
    sections.append("")
    
    for i, msg in enumerate(conversation.messages):
        # Skip system messages - those are instructions we'll re-add for chat
        if msg.role == MessageRole.SYSTEM:
            continue
        
        # Format each message with clear headers
        if msg.role == MessageRole.USER:
            # User messages in investigation are either:
            # - Initial prompt (tools + alert + runbook + task)
            # - Observations (tool results)
            if i == 1:  # First user message after system
                sections.append("### Initial Investigation Request")
                sections.append("")
                sections.append(msg.content)
                sections.append("")
            else:
                # Tool result observation
                sections.append("**Observation:**")
                sections.append("")
                sections.append(msg.content)
                sections.append("")
        
        elif msg.role == MessageRole.ASSISTANT:
            # Assistant messages contain Thought/Action/Final Answer
            sections.append("**Agent Response:**")
            sections.append("")
            sections.append(msg.content)
            sections.append("")
    
    sections.append("=" * 80)
    sections.append("END OF INVESTIGATION HISTORY")
    sections.append("=" * 80)
    sections.append("")
    
    return "\n".join(sections)


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
        Create a new chat for a completed session.
        
        Steps:
        1. Validate session exists and is completed
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
            ValueError: If session not found, not completed, or chat disabled
        """
        # Get session and validate
        session = await self.history_service.get_alert_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != "completed":
            raise ValueError("Can only create chat for completed sessions")
        
        # Check if chat already exists (via history_service)
        existing_chat = await self.history_service.get_chat_by_session(session_id)
        if existing_chat:
            logger.info(f"Chat already exists for session {session_id}")
            return existing_chat
        
        # TODO: Validate chain has chat enabled (implementation detail)
        # This would check chain_definition for chat_enabled=true
        
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
        
        return created_chat
    
    async def send_message(
        self,
        chat_id: str,
        user_question: str,
        author: str
    ) -> str:
        """
        Process a user message and generate assistant response.
        
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
            
        Returns:
            Stage execution ID for this chat response
            
        Raises:
            ValueError: If chat not found or validation fails
            asyncio.TimeoutError: If execution exceeds timeout
            Exception: Other processing errors
        """
        chat_mcp_client = None
        execution_id = None
        
        try:
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
            
            # 3. Build context (initial context OR cumulative from last execution)
            message_context = await self._build_message_context(chat, user_question)
            
            # 4. Create stage execution for this response
            # Uses stage execution context manager (like AlertService)
            stage_execution = StageExecution(
                session_id=chat.session_id,
                stage_id=f"chat-response-{user_msg.message_id}",
                stage_index=0,  # Chat messages don't have meaningful stage index
                stage_name="Chat Response",
                agent="ChatAgent",
                status=StageStatus.PENDING.value,
                chat_id=chat_id,
                chat_user_message_id=user_msg.message_id
            )
            
            # Trigger stage execution hooks (creates DB record, publishes events)
            async with stage_execution_context(chat.session_id, stage_execution) as ctx:
                pass
            
            execution_id = stage_execution.execution_id
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
            
            # 7. Update stage execution to started
            await self._update_stage_execution_started(execution_id)
            
            # 8. Get MCP selection from chat
            mcp_selection = (
                MCPSelectionConfig(**chat.mcp_selection) 
                if chat.mcp_selection 
                else None
            )
            
            # 9. Create session-scoped MCP client for this chat execution
            logger.info(f"Creating MCP client for chat message {execution_id}")
            chat_mcp_client = await self.mcp_client_factory.create_client()
            
            # 10. Create ChatAgent with MCP selection configuration
            chat_agent = self.agent_factory.create_agent(
                agent_name="ChatAgent",
                mcp_client=chat_mcp_client
            )
            
            # Set stage execution ID for interaction tagging
            chat_agent.set_current_stage_execution_id(execution_id)
            
            # 11. Build ChainContext for chat (minimal, for compatibility)
            processing_alert = ProcessingAlert(
                alert_type="chat",  # Special type for chat
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
        and formats it as readable text for the chat agent.
        
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
        
        # Get last interaction - has complete cumulative conversation
        last_interaction = llm_interactions[-1]
        
        # Format as readable text
        return format_conversation_history_as_text(last_interaction.conversation)
    
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
        
        # Get session for metadata
        session = await self.history_service.get_alert_session(session_id)
        
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
        if not session.chain_definition:
            logger.warning(f"No chain definition in session {session.session_id}")
            return None
        
        # Extract unique server names from all stages' default configurations
        server_names = set()
        chain_def = session.chain_definition
        
        for stage in chain_def.get("stages", []):
            agent_name = stage.get("agent")
            if not agent_name:
                continue
            
            # Look up agent's default MCP servers from configuration
            # Try configured agents first, then builtin agents
            if self.agent_factory.agent_configs and agent_name in self.agent_factory.agent_configs:
                agent_config = self.agent_factory.agent_configs[agent_name]
                server_names.update(agent_config.mcp_servers)
            else:
                # Builtin agent - get from builtin config
                from tarsy.config.builtin_config import get_builtin_agent_config
                builtin_config = get_builtin_agent_config(agent_name)
                if builtin_config and "mcp_servers" in builtin_config:
                    server_names.update(builtin_config["mcp_servers"])
        
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
    
    async def _build_message_context(
        self,
        chat: Chat,
        user_question: str
    ) -> ChatMessageContext:
        """
        Build context for new chat message including conversation history.
        
        Strategy for context accumulation:
        - First chat message: Use chat.conversation_history (captured from session)
        - Subsequent messages: Get last chat execution's LLM interactions
          (which naturally includes all previous context + chat Q&A)
        
        This is cumulative - each LLM interaction contains the full history,
        so we just need the most recent one.
        
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
            # (Already formatted during create_chat())
            context_history = chat.conversation_history
        else:
            # Subsequent message - get last chat execution's LLM interactions
            last_exec = prev_executions[-1]
            llm_interactions = await self.history_service.get_llm_interactions_for_stage(
                last_exec.execution_id
            )
            
            if not llm_interactions:
                # Fallback to chat.conversation_history if no interactions found
                logger.warning(f"No LLM interactions found for execution {last_exec.execution_id}, using chat history")
                context_history = chat.conversation_history
            else:
                # Format conversation using common helper (includes previous chat Q&A)
                context_history = await self._get_formatted_conversation_from_llm_interactions(
                    llm_interactions
                )
        
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
            async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
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
            async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
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
            async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as failed")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as failed: {str(e)}")

