"""
Alert Service for multi-layer agent architecture.

This module provides the service that delegates alert processing to
specialized agents based on alert type. It implements the multi-layer
agent architecture for alert processing.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import asyncio
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainStageConfigModel
    from tarsy.models.agent_execution_result import ParallelStageResult
    from tarsy.models.db_models import AlertSession, StageExecution

from tarsy.agents.exceptions import SessionPaused
from tarsy.config.agent_config import ConfigurationError, ConfigurationLoader
from tarsy.config.settings import Settings
from tarsy.integrations.llm.manager import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.integrations.notifications.summarizer import ExecutiveSummaryAgent
from tarsy.models.agent_config import ChainConfigModel
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.api_models import CancelAgentResponse, ChainExecutionResult
from tarsy.models.constants import (
    AlertSessionStatus,
    CancellationReason,
    ChainStatus,
    ParallelType,
    ProgressPhase,
    StageStatus,
    SuccessPolicy,
)
from tarsy.models.pause_metadata import PauseMetadata, PauseReason
from tarsy.models.processing_context import ChainContext
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.chain_registry import ChainRegistry
from tarsy.services.history_service import get_history_service
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.parallel_stage_executor import ParallelStageExecutor
from tarsy.services.response_formatter import (
    format_chain_success_response,
    format_error_response,
)
from tarsy.services.runbook_service import RunbookService
from tarsy.services.session_manager import SessionManager
from tarsy.services.stage_execution_manager import StageExecutionManager
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

logger = get_module_logger(__name__)


class AlertService:
    """
    Service for alert processing with agent delegation.
    
    This class implements a multi-layer architecture that delegates 
    processing to specialized agents based on alert type.
    """
    
    def __init__(self, settings: Settings, runbook_http_client: Optional[httpx.AsyncClient] = None):
        """
        Initialize the alert service with required services.
        
        Args:
            settings: Application settings
            runbook_http_client: Optional HTTP client for runbook service (for testing)
        """
        self.settings = settings
        
        # Load agent configuration first
        self.parsed_config = self._load_agent_configuration()

        # Initialize services
        self.runbook_service = RunbookService(settings, runbook_http_client)
        self.history_service = get_history_service()
        
        # Initialize registries with loaded configuration
        config_loader = ConfigurationLoader(settings.agent_config_path) if settings.agent_config_path else None
        self.chain_registry = ChainRegistry(config_loader)
        self.mcp_server_registry = MCPServerRegistry(
            settings=settings,
            configured_servers=self.parsed_config.mcp_servers
        )
        
        # Initialize services that depend on registries
        # Note: This health check client is ONLY for health monitoring, never for alert processing
        self.health_check_mcp_client = MCPClient(settings, self.mcp_server_registry)
        self.llm_manager = LLMManager(settings)
        
        # Initialize MCP client factory for creating per-session clients
        from tarsy.services.mcp_client_factory import MCPClientFactory
        self.mcp_client_factory = MCPClientFactory(settings, self.mcp_server_registry)
        
        # Initialize manager classes for modular architecture
        self.stage_manager = StageExecutionManager(history_service=self.history_service)
        self.session_manager = SessionManager(history_service=self.history_service)
        
        # Initialize agent factory with dependencies (no MCP client - provided per agent)
        self.agent_factory = None  # Will be initialized in initialize()
        
        # Initialize parallel executor (depends on agent_factory and stage_manager, set in initialize())
        self.parallel_executor: Optional[ParallelStageExecutor] = None
        
        # Reference to MCP health monitor (set during startup in main.py)
        self.mcp_health_monitor = None

        # Initialize final analysis summary agent
        self.final_analysis_summarizer: Optional[ExecutiveSummaryAgent] = None
        
        logger.info(f"AlertService initialized with agent delegation support "
                   f"({len(self.parsed_config.agents)} configured agents, "
                   f"{len(self.parsed_config.mcp_servers)} configured MCP servers)")
        
    def _load_agent_configuration(self):
        """
        Load agent configuration from the configured file path.
        Fails fast if file exists but is invalid (configuration error).
        
        Returns:
            CombinedConfigModel: Parsed configuration with agents and MCP servers
            
        Raises:
            ConfigurationError: If configuration file exists but is invalid
        """
        import os

        from tarsy.models.agent_config import CombinedConfigModel
        
        config_path = self.settings.agent_config_path
        
        # If no path configured, use built-ins
        if not config_path:
            logger.info("No agent configuration path set, using built-in agents only")
            return CombinedConfigModel(agents={}, mcp_servers={})
        
        # If file doesn't exist, use built-ins (OK for dev environments)
        if not os.path.exists(config_path):
            logger.info(f"Agent configuration file not found at {config_path}, using built-in agents only")
            return CombinedConfigModel(agents={}, mcp_servers={})
        
        # File exists - it MUST be valid! Fail fast on errors.
        try:
            config_loader = ConfigurationLoader(config_path)
            parsed_config = config_loader.load_and_validate()
            
            logger.info(f"Successfully loaded agent configuration from {config_path}: "
                       f"{len(parsed_config.agents)} agents, {len(parsed_config.mcp_servers)} MCP servers")
            
            return parsed_config
            
        except ConfigurationError as e:
            logger.critical(f"Agent configuration file exists but is invalid: {e}")
            logger.critical(f"Configuration errors must be fixed. File: {config_path}")
            raise  # Fail fast - configuration error
            
        except Exception as e:
            logger.critical(f"Failed to load agent configuration from {config_path}: {e}")
            raise

    async def initialize(self) -> None:
        """
        Initialize the service and all dependencies.
        Validates configuration completeness (not runtime availability).
        """
        try:
            # Initialize health check MCP client (used ONLY for health monitoring)
            await self.health_check_mcp_client.initialize()
            
            # Check for failed servers and create individual warnings
            failed_servers = self.health_check_mcp_client.get_failed_servers()
            if failed_servers:
                from tarsy.models.system_models import WarningCategory
                from tarsy.services.system_warnings_service import (
                    get_warnings_service,
                )
                warnings = get_warnings_service()
                
                for server_id, error_msg in failed_servers.items():
                    logger.critical(f"MCP server '{server_id}' failed to initialize: {error_msg}")
                    # Use standardized warning message format for consistency with health monitor
                    from tarsy.services.mcp_health_monitor import _mcp_warning_message
                    warnings.add_warning(
                        category=WarningCategory.MCP_INITIALIZATION,
                        message=_mcp_warning_message(server_id),
                        details=(
                            f"Failed to initialize during startup: {error_msg}\n\n"
                            f"Check {server_id} configuration and connectivity. "
                            f"The health monitor will automatically clear this warning when the server becomes available."
                        ),
                        server_id=server_id,
                    )

            # Validate that configured LLM provider NAME exists in configuration
            # Note: We check configuration, not runtime availability (API keys work, etc)
            configured_provider = self.settings.llm_provider
            available_providers = self.llm_manager.list_available_providers()

            if configured_provider not in available_providers:
                raise Exception(
                    f"Configured LLM provider '{configured_provider}' not found in loaded configuration. "
                    f"Available providers: {available_providers}. "
                    f"Check your llm_providers.yaml and LLM_PROVIDER environment variable. "
                    f"Note: Provider must be defined and have an API key configured."
                )

            # Validate at least one LLM provider is available
            # This checks if ANY provider initialized (has config and API key)
            if not self.llm_manager.is_available():
                status = self.llm_manager.get_availability_status()
                raise Exception(
                    f"No LLM providers are available. "
                    f"At least one provider must have a valid API key. "
                    f"Provider status: {status}"
                )
            
            # Check for failed LLM providers and create individual warnings
            # Note: Only providers with API keys that failed to initialize are tracked
            failed_providers = self.llm_manager.get_failed_providers()
            if failed_providers:
                from tarsy.models.system_models import WarningCategory
                from tarsy.services.system_warnings_service import (
                    get_warnings_service,
                )
                warnings = get_warnings_service()
                
                for provider_name, error_msg in failed_providers.items():
                    logger.critical(f"LLM provider '{provider_name}' failed to initialize: {error_msg}")
                    warnings.add_warning(
                        WarningCategory.LLM_INITIALIZATION,
                        f"LLM Provider '{provider_name}' failed to initialize: {error_msg}",
                        details=f"Check {provider_name} configuration (base_url, SSL settings, network connectivity). This provider will be unavailable.",
                    )

            # Initialize agent factory with dependencies (no MCP client - provided per agent)
            self.agent_factory = AgentFactory(
                llm_manager=self.llm_manager,
                mcp_registry=self.mcp_server_registry,
                agent_configs=self.parsed_config.agents,
            )

            # Initialize parallel executor now that agent_factory is ready
            self.parallel_executor = ParallelStageExecutor(
                agent_factory=self.agent_factory,
                settings=self.settings,
                stage_manager=self.stage_manager,
            )

            # Initialize final result summarizer with LLM manager
            self.final_analysis_summarizer = ExecutiveSummaryAgent(
                llm_manager=self.llm_manager,
            )

            logger.info("AlertService initialized successfully")
            logger.info(f"Using LLM provider: {configured_provider}")

        except Exception as e:
            logger.error(f"Failed to initialize AlertService: {str(e)}")
            raise
    
    async def process_alert(
        self, 
        chain_context: ChainContext
    ) -> str:
        """
        Process an alert by delegating to the appropriate specialized agent.
        
        Creates a session-scoped MCP client for isolation and proper resource cleanup.
        
        Args:
            chain_context: Chain context with all processing data
            
        Returns:
            Analysis result as a string
        """
        # Create session-scoped MCP client for this alert processing
        session_mcp_client = None
        
        try:
            # Step 1: Validate prerequisites
            if not self.llm_manager.is_available():
                raise Exception("Cannot process alert: No LLM providers are available")
                
            if not self.agent_factory:
                raise Exception("Agent factory not initialized - call initialize() first")
            
            # Step 2: Create isolated MCP client for this session
            logger.info(f"Creating session-scoped MCP client for session {chain_context.session_id}")
            session_mcp_client = await self.mcp_client_factory.create_client()
            logger.debug(f"Session-scoped MCP client created for session {chain_context.session_id}")
            
            # Step 3: Get chain for alert type
            try:
                chain_definition = self.chain_registry.get_chain_for_alert_type(chain_context.processing_alert.alert_type)
            except ValueError as e:
                error_msg = str(e)
                logger.error(f"Chain selection failed: {error_msg}")
                
                # Update history session with error
                self.session_manager.update_session_error(chain_context.session_id, error_msg)
                    
                return format_error_response(chain_context, error_msg)
            
            logger.info(f"Selected chain '{chain_definition.chain_id}' for alert type '{chain_context.processing_alert.alert_type}'")
            
            # Create history session with chain info
            session_created = self.session_manager.create_chain_history_session(chain_context, chain_definition)
            
            # Mark session as being processed by this pod
            if session_created and self.history_service:
                from tarsy.main import get_pod_id
                pod_id = get_pod_id()
                
                if pod_id == "unknown":
                    logger.warning(
                        "TARSY_POD_ID not set - all pods will share pod_id='unknown'. "
                        "This breaks graceful shutdown in multi-replica deployments. "
                        "Set TARSY_POD_ID in Kubernetes pod spec."
                    )
                
                await self.history_service.start_session_processing(
                    chain_context.session_id, 
                    pod_id
                )
            
            # Publish session.created event if session was created
            if session_created:
                from tarsy.services.events.event_helpers import publish_session_created
                await publish_session_created(
                    chain_context.session_id,
                    chain_context.processing_alert.alert_type
                )
            
            # Update history session with processing start
            self.session_manager.update_session_status(chain_context.session_id, AlertSessionStatus.IN_PROGRESS.value)
            
            # Publish session.started event
            from tarsy.services.events.event_helpers import publish_session_started
            await publish_session_started(
                chain_context.session_id,
                chain_context.processing_alert.alert_type
            )
            
            # Step 4: Extract runbook from alert data and download once per chain
            # If no runbook URL provided, use the built-in default runbook
            runbook = chain_context.processing_alert.runbook_url
            if runbook:
                logger.debug(f"Downloading runbook from: {runbook}")
                runbook_content = await self.runbook_service.download_runbook(runbook)
            else:
                logger.debug("No runbook URL provided, using built-in default runbook")
                from tarsy.config.builtin_config import DEFAULT_RUNBOOK_CONTENT
                runbook_content = DEFAULT_RUNBOOK_CONTENT
            
            # Step 5: Set up chain context
            chain_context.set_chain_context(chain_definition.chain_id)
            chain_context.set_runbook_content(runbook_content)
            
            # Step 6: Execute chain stages sequentially with configurable timeout
            try:
                chain_result = await asyncio.wait_for(
                    self._execute_chain_stages(
                        chain_definition=chain_definition,
                        chain_context=chain_context,
                        session_mcp_client=session_mcp_client
                    ),
                    timeout=self.settings.alert_processing_timeout
                )
            except asyncio.TimeoutError:
                error_msg = f"Alert processing exceeded {self.settings.alert_processing_timeout}s timeout"
                logger.error(f"{error_msg} for session {chain_context.session_id}")
                # Update history session with timeout error
                self.session_manager.update_session_error(chain_context.session_id, error_msg)
                # Publish session.failed event
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(chain_context.session_id)
                return format_error_response(chain_context, error_msg)
            
            # Step 7: Format and return results
            if chain_result.status == ChainStatus.COMPLETED:
                analysis = chain_result.final_analysis or 'No analysis provided'
                
                # Format final result with chain context
                final_result = format_chain_success_response(
                    chain_context,
                    chain_definition,
                    analysis,
                    chain_result.timestamp_us
                )
                
                # Publish progress update event for executive summary generation
                from tarsy.services.events.event_helpers import (
                    publish_session_progress_update,
                )
                await publish_session_progress_update(
                    chain_context.session_id,
                    phase=ProgressPhase.SUMMARIZING,
                    metadata=None
                )
                
                # Generate executive summary for dashboard display and external notifications
                # Use chain-level provider for executive summary (or global if not set)
                final_result_summary = await self.final_analysis_summarizer.generate_executive_summary(
                    content=analysis,
                    session_id=chain_context.session_id,
                    provider=chain_definition.llm_provider
                )

                # Mark history session as completed successfully
                self.session_manager.update_session_status(
                    chain_context.session_id, 
                    AlertSessionStatus.COMPLETED.value,
                    final_analysis=final_result,
                    final_analysis_summary=final_result_summary
                )
                
                # Publish session.completed event
                from tarsy.services.events.event_helpers import (
                    publish_session_completed,
                )
                await publish_session_completed(chain_context.session_id)
                return final_result
            elif chain_result.status == ChainStatus.PAUSED:
                # Session was paused - this is not an error condition
                # Status was already updated to PAUSED and pause event was already published in _execute_chain_stages
                logger.info(f"Session {chain_context.session_id} paused successfully")
                
                # Return a response indicating pause (not an error)
                pause_message = chain_result.final_analysis or "Session paused - waiting for user to resume"
                return format_chain_success_response(
                    chain_context,
                    chain_definition,
                    pause_message,
                    chain_result.timestamp_us
                )
            else:
                # Handle chain processing error
                error_msg = chain_result.error or 'Chain processing failed'
                logger.error(f"Chain processing failed: {error_msg}")
                
                # Update history session with processing error
                self.session_manager.update_session_error(chain_context.session_id, error_msg)
                
                # Publish session.failed event
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(chain_context.session_id)
                
                return format_error_response(chain_context, error_msg)
                
        except Exception as e:
            error_msg = f"Alert processing failed: {str(e)}"
            logger.error(error_msg)
            
            # Update history session with processing error
            self.session_manager.update_session_error(chain_context.session_id, error_msg)
            
            # Publish session.failed event
            from tarsy.services.events.event_helpers import publish_session_failed
            await publish_session_failed(chain_context.session_id)
            
            return format_error_response(chain_context, error_msg)
        
        finally:
            # Always cleanup session-scoped MCP client
            if session_mcp_client:
                try:
                    logger.debug(f"Closing session-scoped MCP client for session {chain_context.session_id}")
                    await session_mcp_client.close()
                    logger.debug(f"Session-scoped MCP client closed for session {chain_context.session_id}")
                except Exception as cleanup_error:
                    # Log but don't raise - cleanup errors shouldn't fail the session
                    logger.warning(f"Error closing session MCP client: {cleanup_error}")
    
    async def cancel_agent(
        self,
        session_id: str,
        execution_id: str
    ) -> CancelAgentResponse:
        """
        Cancel individual parallel agent and re-evaluate stage status.
        
        Steps:
        1. Validate inputs and load child stage execution
        2. Update child stage to CANCELLED status with paused_at_us as completed_at_us
        3. Load all sibling stages (same parent_stage_execution_id)
        4. Run aggregate_status() logic on all children
        5. Update parent stage status based on aggregation
        6. Update session status if applicable
        7. Publish events for real-time UI updates
        
        Args:
            session_id: Session ID
            execution_id: Child stage execution ID to cancel
            
        Returns:
            CancelAgentResponse with success status and updated statuses
            
        Raises:
            ValueError: If validation fails (not found, not paused, etc.)
            Exception: If cancellation fails
        """
        if not self.history_service:
            raise ValueError("History service not available")
        
        # Step 1: Validate session exists and is paused
        session = self.history_service.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != AlertSessionStatus.PAUSED.value:
            raise ValueError(f"Session {session_id} is not paused (status: {session.status})")
        
        # Step 2: Load child stage execution
        child_stage = await self.history_service.get_stage_execution(execution_id)
        if not child_stage:
            raise ValueError(f"Stage execution {execution_id} not found")
        
        if child_stage.session_id != session_id:
            raise ValueError(f"Stage execution {execution_id} does not belong to session {session_id}")
        
        if not child_stage.parent_stage_execution_id:
            raise ValueError(f"Stage execution {execution_id} is not a child stage (no parent)")
        
        if child_stage.status != StageStatus.PAUSED.value:
            raise ValueError(f"Stage execution {execution_id} is not paused (status: {child_stage.status})")
        
        logger.info(f"Canceling paused agent {child_stage.agent} (execution_id: {execution_id})")
        
        # Step 3: Update child stage to CANCELLED
        child_stage.status = StageStatus.CANCELLED.value
        child_stage.error_message = "Cancelled by user"
        
        # Use paused_at_us as completed_at_us for accurate duration
        if child_stage.paused_at_us:
            child_stage.completed_at_us = child_stage.paused_at_us
        else:
            # Fallback if paused_at_us is somehow None (shouldn't happen)
            logger.warning(f"paused_at_us is None for {execution_id}, using now_us()")
            child_stage.completed_at_us = now_us()
        
        # Calculate duration in milliseconds
        if child_stage.started_at_us and child_stage.completed_at_us:
            duration_us = child_stage.completed_at_us - child_stage.started_at_us
            child_stage.duration_ms = int(duration_us / 1000)
        
        # Persist the updated child stage
        await self.history_service.update_stage_execution(child_stage)
        
        # Trigger hooks for child stage update
        from tarsy.hooks.hook_context import stage_execution_context
        async with stage_execution_context(child_stage):
            pass  # Hooks are triggered on context enter/exit
        
        # Step 4: Load all sibling stages for aggregation
        all_children = await self.history_service.get_parallel_stage_children(
            child_stage.parent_stage_execution_id
        )
        
        # Step 5: Create metadata list for aggregation
        # Transform StageExecution DB models → AgentExecutionMetadata for aggregate_status()
        # Only the 'status' field is critical for aggregation; other fields are informational
        from tarsy.models.agent_execution_result import AgentExecutionMetadata
        metadatas = []
        for sibling in all_children:
            metadata = AgentExecutionMetadata(
                agent_name=sibling.agent,
                llm_provider="unknown",  # Not used in aggregation logic
                iteration_strategy="unknown",  # Not used in aggregation logic
                started_at_us=sibling.started_at_us or 0,
                completed_at_us=sibling.completed_at_us or 0,
                status=StageStatus(sibling.status),  # ← Key field for aggregation
                error_message=sibling.error_message,
                token_usage=None
            )
            metadatas.append(metadata)
        
        # Step 6: Load parent stage to get success_policy
        parent_stage = await self.history_service.get_stage_execution(
            child_stage.parent_stage_execution_id
        )
        if not parent_stage:
            raise Exception(f"Parent stage {child_stage.parent_stage_execution_id} not found")
        
        # Get success_policy from stage_output metadata if available
        success_policy = SuccessPolicy.ANY  # Default
        if parent_stage.stage_output and isinstance(parent_stage.stage_output, dict):
            metadata_dict = parent_stage.stage_output.get("metadata", {})
            if isinstance(metadata_dict, dict):
                policy_str = metadata_dict.get("success_policy", "any")
                try:
                    success_policy = SuccessPolicy(policy_str)
                except ValueError:
                    success_policy = SuccessPolicy.ANY
        
        # Run aggregation logic
        aggregated_status = self.parallel_executor.aggregate_status(metadatas, success_policy)
        
        logger.info(f"Aggregated status after cancel: {aggregated_status.value}")
        
        # Step 7: Update parent stage if status changed
        if aggregated_status != StageStatus.PAUSED:
            parent_stage.status = aggregated_status.value
            if aggregated_status == StageStatus.COMPLETED:
                parent_stage.completed_at_us = now_us()
                # Calculate parent duration
                if parent_stage.started_at_us:
                    duration_us = parent_stage.completed_at_us - parent_stage.started_at_us
                    parent_stage.duration_ms = int(duration_us / 1000)
            elif aggregated_status == StageStatus.FAILED:
                parent_stage.completed_at_us = now_us()
                parent_stage.error_message = "Parallel stage failed after agent cancellation"
                # Calculate parent duration
                if parent_stage.started_at_us:
                    duration_us = parent_stage.completed_at_us - parent_stage.started_at_us
                    parent_stage.duration_ms = int(duration_us / 1000)
            
            # Persist the updated parent stage
            await self.history_service.update_stage_execution(parent_stage)
            
            # Trigger hooks for parent stage update
            async with stage_execution_context(parent_stage):
                pass
        
        # Step 8: Update session if stage completed or failed
        new_session_status = session.status
        if aggregated_status == StageStatus.COMPLETED:
            # Parallel stage completed - need to run synthesis and continue chain
            # Don't mark session as completed yet; trigger chain continuation
            logger.info("Parallel stage completed after agent cancellation - triggering chain continuation")
            
            # Change session status to IN_PROGRESS to allow continuation
            self.session_manager.update_session_status(session_id, AlertSessionStatus.IN_PROGRESS.value)
            
            # Publish session resumed event to update UI
            from tarsy.services.events.event_helpers import publish_session_resumed
            await publish_session_resumed(session_id)
            
            # Trigger background task to continue chain execution (synthesis + remaining stages)
            import asyncio
            asyncio.create_task(self._continue_after_parallel_completion(session_id, parent_stage.execution_id))
            
            # Return early - chain continuation will handle final session status
            return CancelAgentResponse(
                success=True,
                session_status=AlertSessionStatus.IN_PROGRESS.value,
                stage_status=aggregated_status.value
            )
            
        elif aggregated_status == StageStatus.FAILED:
            # Check if all non-completed agents were cancelled
            # If so, treat the session as cancelled rather than failed
            cancelled_count = sum(1 for m in metadatas if m.status == StageStatus.CANCELLED)
            failed_count = sum(1 for m in metadatas if m.status == StageStatus.FAILED)
            
            if cancelled_count > 0 and failed_count == 0:
                # All non-completed agents were cancelled - treat as session cancellation
                new_session_status = AlertSessionStatus.CANCELLED.value
                session.status = new_session_status
                session.completed_at_us = now_us()
                session.error_message = None  # Clear error message for cancellation
                
                # Update session
                self.session_manager.update_session_status(session_id, new_session_status)
                
                # Publish session cancelled event
                from tarsy.services.events.event_helpers import publish_session_cancelled
                await publish_session_cancelled(session_id)
            else:
                # Session fails (some agents failed, not just cancelled)
                new_session_status = AlertSessionStatus.FAILED.value
                session.status = new_session_status
                session.completed_at_us = now_us()
                session.error_message = "Stage failed after agent cancellation"
                
                # Update session
                self.session_manager.update_session_status(
                    session_id, 
                    new_session_status, 
                    error_message="Stage failed after agent cancellation"
                )
                
                # Publish session failed event
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(session_id)
        
        # Step 9: Publish agent cancelled event
        from tarsy.services.events.event_helpers import publish_agent_cancelled
        await publish_agent_cancelled(
            session_id=session_id,
            execution_id=execution_id,
            agent_name=child_stage.agent,
            parent_stage_execution_id=child_stage.parent_stage_execution_id
        )
        
        return CancelAgentResponse(
            success=True,
            session_status=new_session_status,
            stage_status=aggregated_status.value
        )
    
    async def _continue_after_parallel_completion(
        self,
        session_id: str,
        parent_stage_execution_id: str
    ) -> None:
        """
        Continue chain execution after parallel stage completes via agent cancellation.
        
        This runs synthesis on the completed parallel stage and continues to any remaining stages.
        Reuses the same continuation logic as resume_paused_session by treating the completed
        parallel stage similarly to a resumed parallel stage.
        
        Args:
            session_id: Session ID
            parent_stage_execution_id: Parent parallel stage execution ID that just completed
        """
        session_mcp_client = None
        
        try:
            logger.info(f"Starting chain continuation after parallel stage completion: {session_id}")
            
            # Get session and find the completed parallel stage
            session = self.history_service.get_session(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")
            
            stage_executions = await self.history_service.get_stage_executions(session_id)
            
            completed_parent_stage = None
            for stage_exec in stage_executions:
                if stage_exec.execution_id == parent_stage_execution_id:
                    completed_parent_stage = stage_exec
                    break
            
            if not completed_parent_stage:
                raise Exception(f"Parent stage {parent_stage_execution_id} not found")
            
            # Reconstruct context and chain definition
            chain_context, chain_definition = await self._reconstruct_session_context(
                session, stage_executions, completed_parent_stage.stage_name
            )
            
            # Initialize MCP client
            session_mcp_client = await self.mcp_client_factory.create_client()
            
            # Find stage index
            stage_index = completed_parent_stage.stage_index
            stage_config = chain_definition.stages[stage_index]
            
            # Reconstruct ParallelStageResult from completed parent stage
            from tarsy.models.agent_execution_result import ParallelStageResult
            parallel_result = ParallelStageResult.model_validate(completed_parent_stage.stage_output)
            
            # Continue from parallel completion (synthesis + remaining stages)
            await self._continue_from_parallel_completion(
                session_id=session_id,
                parallel_result=parallel_result,
                completed_parent_stage=completed_parent_stage,
                stage_config=stage_config,
                stage_index=stage_index,
                stage_executions=stage_executions,
                chain_context=chain_context,
                chain_definition=chain_definition,
                session_mcp_client=session_mcp_client
            )
                
        except Exception as e:
            logger.error(f"Failed to continue chain after parallel completion: {e}", exc_info=True)
            self.session_manager.update_session_status(
                session_id,
                AlertSessionStatus.FAILED.value,
                error_message=f"Failed to continue after parallel completion: {str(e)}"
            )
            from tarsy.services.events.event_helpers import publish_session_failed
            await publish_session_failed(session_id)
        finally:
            if session_mcp_client:
                try:
                    await session_mcp_client.close()
                except Exception as cleanup_error:
                    logger.warning(f"Error closing session MCP client: {cleanup_error}")
    
    async def _reconstruct_session_context(
        self,
        session: "AlertSession",
        stage_executions: list["StageExecution"],
        current_stage_name: str
    ) -> tuple[ChainContext, ChainConfigModel]:
        """
        Reconstruct ChainContext and ChainDefinition from session data.
        
        Args:
            session: AlertSession object
            stage_executions: List of stage executions for this session
            current_stage_name: Name of the current stage
            
        Returns:
            Tuple of (ChainContext, ChainConfigModel)
        """
        from tarsy.models.alert import ProcessingAlert
        
        # Reconstruct ProcessingAlert
        processing_alert = ProcessingAlert(
            alert_type=session.alert_type or "unknown",
            timestamp=session.started_at_us,
            runbook_url=session.runbook_url,
            alert_data=session.alert_data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=session.session_id,
            current_stage_name=current_stage_name,
            author=session.author
        )
        
        # Restore MCP selection if present
        if session.mcp_selection:
            from tarsy.models.mcp_selection_models import MCPSelectionConfig
            chain_context.mcp = MCPSelectionConfig.model_validate(session.mcp_selection)
        
        # Reconstruct stage results from completed stages (and paused for resume scenarios)
        for stage_exec in stage_executions:
            if stage_exec.stage_output and stage_exec.status in [StageStatus.COMPLETED.value, StageStatus.PAUSED.value]:
                if stage_exec.parallel_type in ParallelType.parallel_values() and not stage_exec.parent_stage_execution_id:
                    from tarsy.models.agent_execution_result import ParallelStageResult
                    result = ParallelStageResult.model_validate(stage_exec.stage_output)
                else:
                    result = AgentExecutionResult.model_validate(stage_exec.stage_output)
                chain_context.add_stage_result(stage_exec.execution_id, result)
                
                if stage_exec.status == StageStatus.PAUSED.value:
                    logger.info(f"Restored paused stage '{stage_exec.stage_name}' with execution_id {stage_exec.execution_id}")
        
        # Get chain definition
        chain_definition = session.chain_config
        if not chain_definition:
            raise Exception("Chain definition not found in session")
        
        return chain_context, chain_definition
    
    async def _continue_from_parallel_completion(
        self,
        session_id: str,
        parallel_result: "ParallelStageResult",
        completed_parent_stage: "StageExecution",
        stage_config: "ChainStageConfigModel",
        stage_index: int,
        stage_executions: list["StageExecution"],
        chain_context: ChainContext,
        chain_definition: ChainConfigModel,
        session_mcp_client: MCPClient
    ) -> None:
        """
        Continue chain execution after a parallel stage completes.
        
        Runs synthesis on the completed parallel stage and continues to any remaining stages.
        
        Args:
            session_id: Session ID
            parallel_result: Result from the completed parallel stage
            completed_parent_stage: The completed parallel parent stage execution
            stage_config: Stage configuration
            stage_index: Index of the stage in chain definition
            stage_executions: All stage executions for this session
            chain_context: Reconstructed chain context
            chain_definition: Chain definition
            session_mcp_client: Session-scoped MCP client
        """
        logger.info(f"Running synthesis for completed parallel stage: {completed_parent_stage.stage_name}")
        
        # Get count of non-child stages for synthesis index
        non_child_stages = [s for s in stage_executions if s.parent_stage_execution_id is None]
        synthesis_index = len(non_child_stages)
        
        synthesis_execution_id, synthesis_result = await self.parallel_executor.synthesize_parallel_results(
            parallel_result, chain_context, session_mcp_client, stage_config, chain_definition, synthesis_index
        )
        chain_context.add_stage_result(synthesis_execution_id, synthesis_result)
        
        # Check if there are more stages after this
        next_stage_idx = stage_index + 1
        if next_stage_idx < len(chain_definition.stages):
            # More stages to execute
            logger.info(f"Continuing to next stage: {chain_definition.stages[next_stage_idx].name}")
            chain_context.current_stage_name = chain_definition.stages[next_stage_idx].name
            
            result = await self._execute_chain_stages(
                chain_definition,
                chain_context,
                session_mcp_client,
            )

            # Determine success from status and use final_analysis as the chain output
            if result.status == ChainStatus.COMPLETED:
                final_result = result.final_analysis or "No analysis provided"

                # Generate executive summary
                summary = await self.final_analysis_summarizer.generate_executive_summary(
                    content=final_result,
                    session_id=session_id,
                    provider=chain_definition.llm_provider
                )

                self.session_manager.update_session_status(
                    session_id,
                    AlertSessionStatus.COMPLETED.value,
                    final_analysis=final_result,
                    final_analysis_summary=summary
                )
                from tarsy.services.events.event_helpers import publish_session_completed
                await publish_session_completed(session_id)
            else:
                self.session_manager.update_session_status(
                    session_id,
                    AlertSessionStatus.FAILED.value,
                    error_message=result.error or "Chain execution failed",
                )
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(session_id)
        else:
            # No more stages - this was the last one, extract final analysis
            logger.info("No more stages after synthesis - session complete")
            final_result = synthesis_result.result_summary
            
            # Generate executive summary
            summary = await self.final_analysis_summarizer.generate_executive_summary(
                content=final_result,
                session_id=session_id,
                provider=chain_definition.llm_provider
            )
            
            self.session_manager.update_session_status(
                session_id,
                AlertSessionStatus.COMPLETED.value,
                final_analysis=final_result,
                final_analysis_summary=summary
            )
            from tarsy.services.events.event_helpers import publish_session_completed
            await publish_session_completed(session_id)
    
    async def resume_paused_session(self, session_id: str) -> str:
        """
        Resume a paused session from where it left off.
        
        Reconstructs the session state from database and continues execution.
        
        Args:
            session_id: The session ID to resume
            
        Returns:
            Analysis result as a string
            
        Raises:
            Exception: If session not found, not paused, or resume fails
        """
        session_mcp_client = None
        
        try:
            # Step 1: Validate session exists and is paused
            if not self.history_service:
                raise Exception("History service not available")
            
            session = self.history_service.get_session(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")
            
            if session.status != AlertSessionStatus.PAUSED.value:
                raise Exception(f"Session {session_id} is not paused (status: {session.status})")
            
            logger.info(f"Resuming paused session {session_id}")
            
            # Step 2: Get all stage executions for this session
            stage_executions = await self.history_service.get_stage_executions(session_id)
            
            # Find paused stage
            paused_stage = None
            for stage_exec in stage_executions:
                if stage_exec.status == StageStatus.PAUSED.value:
                    paused_stage = stage_exec
                    break
            
            if not paused_stage:
                raise Exception(f"No paused stage found for session {session_id}")
            
            logger.info(f"Found paused stage: {paused_stage.stage_name} at iteration {paused_stage.current_iteration}")
            
            # Step 3: Reconstruct ChainContext from session data (using helper)
            chain_context, chain_definition = await self._reconstruct_session_context(
                session, stage_executions, paused_stage.stage_name
            )
            
            # Get ProcessingAlert for runbook handling
            from tarsy.models.alert import ProcessingAlert
            processing_alert = ProcessingAlert(
                alert_type=session.alert_type or "unknown",
                timestamp=session.started_at_us,
                runbook_url=session.runbook_url,
                alert_data=session.alert_data
            )
            
            chain_context.set_chain_context(chain_definition.chain_id, paused_stage.stage_name)
            
            # Download runbook if needed
            runbook_url = processing_alert.runbook_url
            if runbook_url:
                runbook_content = await self.runbook_service.download_runbook(runbook_url)
            else:
                from tarsy.config.builtin_config import DEFAULT_RUNBOOK_CONTENT
                runbook_content = DEFAULT_RUNBOOK_CONTENT
            
            chain_context.set_runbook_content(runbook_content)
            
            # Step 5: Update session status to IN_PROGRESS
            self.session_manager.update_session_status(session_id, AlertSessionStatus.IN_PROGRESS.value)
            
            # Publish resume event
            from tarsy.services.events.event_helpers import publish_session_resumed
            await publish_session_resumed(session_id)
            
            # Step 6: Create new MCP client and continue execution
            # Note: Stage status transition from PAUSED→ACTIVE is handled in _update_stage_execution_started
            logger.info(f"Creating session-scoped MCP client for resumed session {session_id}")
            session_mcp_client = await self.mcp_client_factory.create_client()
            
            # Check if paused stage is a parallel stage
            if paused_stage.parallel_type in ParallelType.parallel_values():
                logger.info(f"Resuming parallel stage '{paused_stage.stage_name}'")
                
                # Find stage index in chain definition
                stage_index = paused_stage.stage_index
                
                # Resume parallel stage (only re-executes paused children)
                parallel_result = await self.parallel_executor.resume_parallel_stage(
                    paused_parent_stage=paused_stage,
                    chain_context=chain_context,
                    session_mcp_client=session_mcp_client,
                    chain_definition=chain_definition,
                    stage_index=stage_index,
                    history_service=self.history_service
                )
                
                # Add result to context (use paused parent's execution_id as key)
                chain_context.add_stage_result(paused_stage.execution_id, parallel_result)
                
                # Check if we need to continue to next stages
                if parallel_result.status == StageStatus.COMPLETED:
                    # Use helper method to handle synthesis + continuation
                    logger.info("Parallel stage completed after resume - continuing with synthesis")
                    
                    # Get fresh stage executions for synthesis index calculation
                    existing_stages = await self.history_service.get_stage_executions(session_id)
                    stage_config = chain_definition.stages[stage_index]
                    
                    # Note: This is called in async context, not returned
                    # We still need to capture the result for the rest of the resume flow
                    # So we'll inline the continuation logic but keep it consistent
                    await self._continue_from_parallel_completion(
                        session_id=session_id,
                        parallel_result=parallel_result,
                        completed_parent_stage=paused_stage,
                        stage_config=stage_config,
                        stage_index=stage_index,
                        stage_executions=existing_stages,
                        chain_context=chain_context,
                        chain_definition=chain_definition,
                        session_mcp_client=session_mcp_client
                    )
                    
                    # Return early - continuation helper handles everything
                    return "Session completed after parallel stage continuation"
                elif parallel_result.status == StageStatus.PAUSED:
                    # Paused again - need to update session status and publish event
                    # (unlike normal _execute_chain_stages path, parallel resume doesn't do this automatically)
                    logger.warning(f"Parallel stage '{paused_stage.stage_name}' paused again during resume")
                    
                    # Extract pause metadata from the merged result
                    # The parallel executor creates pause metadata when agents hit max_iterations
                    pause_meta = None
                    for agent_result in parallel_result.results:
                        if agent_result.status == StageStatus.PAUSED:
                            # Found a paused agent - create pause metadata
                            from tarsy.models.pause_metadata import (
                                PauseMetadata,
                                PauseReason,
                            )
                            pause_meta = PauseMetadata(
                                reason=PauseReason.MAX_ITERATIONS_REACHED,
                                current_iteration=0,  # Not meaningful for parallel stages
                                message=f"Agent '{agent_result.agent_name}' paused during resume - click resume to continue",
                                paused_at_us=now_us()
                            )
                            break
                    
                    # Update session status to PAUSED with metadata
                    pause_meta_dict = pause_meta.model_dump(mode='json') if pause_meta else None
                    self.session_manager.update_session_status(
                        session_id, 
                        AlertSessionStatus.PAUSED.value,
                        pause_metadata=pause_meta_dict
                    )
                    
                    # Publish pause event for dashboard updates
                    from tarsy.services.events.event_helpers import (
                        publish_session_paused,
                    )
                    await publish_session_paused(session_id)
                    
                    result = ChainExecutionResult(
                        status=ChainStatus.PAUSED,
                        stage_results=[],
                        final_analysis=f"Parallel stage '{paused_stage.stage_name}' paused again",
                        timestamp_us=now_us()
                    )
                else:  # FAILED
                    result = ChainExecutionResult(
                        status=ChainStatus.FAILED,
                        stage_results=[],
                        error=f"Parallel stage '{paused_stage.stage_name}' failed",
                        timestamp_us=now_us()
                    )
            else:
                # Existing: Resume single-agent stage
                result = await self._execute_chain_stages(
                    chain_definition,
                    chain_context,
                    session_mcp_client
                )
            
            # Handle result
            if result.status == ChainStatus.COMPLETED:
                analysis = result.final_analysis or "No analysis provided"
                final_result = format_chain_success_response(
                    chain_context,
                    chain_definition,
                    analysis,
                    result.timestamp_us,
                )
                
                # Publish progress update event for executive summary generation
                from tarsy.services.events.event_helpers import (
                    publish_session_progress_update,
                )
                await publish_session_progress_update(
                    session_id,
                    phase=ProgressPhase.SUMMARIZING,
                    metadata=None
                )
                
                # Generate executive summary for resumed sessions too
                # Use chain-level provider for executive summary (or global if not set)
                final_result_summary = await self.final_analysis_summarizer.generate_executive_summary(
                    content=analysis,
                    session_id=session_id,
                    provider=chain_definition.llm_provider
                )
                
                self.session_manager.update_session_status(
                    session_id,
                    AlertSessionStatus.COMPLETED.value,
                    final_analysis=final_result,
                    final_analysis_summary=final_result_summary,
                )
                from tarsy.services.events.event_helpers import (
                    publish_session_completed,
                )
                await publish_session_completed(session_id)
                return final_result
            elif result.status == ChainStatus.PAUSED:
                # Session paused again - this is normal, not an error
                # Status already updated to PAUSED and pause event already published
                # (either in parallel resume path above, or in _execute_chain_stages for non-parallel)
                logger.info(f"Resumed session {session_id} paused again (hit max iterations)")
                # Format the pause message consistently with initial execution path
                pause_message = result.final_analysis or "Session paused again - waiting for user to resume"
                return format_chain_success_response(
                    chain_context,
                    chain_definition,
                    pause_message,
                    result.timestamp_us,
                )
            else:
                error_msg = result.error or "Chain execution failed"
                self.session_manager.update_session_status(session_id, AlertSessionStatus.FAILED.value)
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(session_id)
                return format_error_response(chain_context, error_msg)
        
        except Exception as e:
            error_msg = f"Failed to resume session: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.session_manager.update_session_error(session_id, error_msg)
            raise
        
        finally:
            # Clean up MCP client
            if session_mcp_client:
                try:
                    await session_mcp_client.close()
                    logger.debug(f"Session-scoped MCP client closed for resumed session {session_id}")
                except Exception as cleanup_error:
                    logger.warning(f"Error closing session MCP client: {cleanup_error}")

    async def _execute_chain_stages(
        self, 
        chain_definition: ChainConfigModel, 
        chain_context: ChainContext,
        session_mcp_client: MCPClient
    ) -> ChainExecutionResult:
        """
        Execute chain stages sequentially with accumulated data flow.
        
        Args:
            chain_definition: Chain definition with stages
            chain_context: Chain context with all processing data
            session_mcp_client: Session-scoped MCP client for all stages in this chain
            
        Returns:
            ChainExecutionResult with execution results
        """
        # Initialize timestamp to prevent UnboundLocalError in exception cases
        timestamp_us = None
        
        try:
            logger.info(f"Starting chain execution '{chain_definition.chain_id}' with {len(chain_definition.stages)} stages")
            
            successful_stages = 0
            failed_stages = 0
            
            # Execute each stage sequentially
            # If resuming, skip stages before the current stage
            start_from_stage = 0
            if chain_context.current_stage_name:
                # Find the index of the current stage to resume from
                for i, stage in enumerate(chain_definition.stages):
                    if stage.name == chain_context.current_stage_name:
                        start_from_stage = i
                        logger.info(f"Resuming from stage {i+1}: '{stage.name}'")
                        break
            
            # Track actual executed stage count (including dynamically added synthesis stages)
            # When resuming, count existing stages to get accurate count
            if chain_context.current_stage_name:
                existing_stages = await self.history_service.get_stage_executions(chain_context.session_id)
                # Filter to non-parallel-child stages (parents and single stages only)
                non_child_stages = [s for s in existing_stages if s.parent_stage_execution_id is None]
                executed_stage_count = len(non_child_stages)
                logger.info(f"Resuming with {executed_stage_count} stages already executed")
            else:
                executed_stage_count = start_from_stage
            
            for i, stage in enumerate(chain_definition.stages):
                # Skip stages before the resume point
                if i < start_from_stage:
                    logger.debug(f"Skipping already completed stage {i+1}: '{stage.name}'")
                    continue
                    
                logger.info(f"Executing stage {i+1}/{len(chain_definition.stages)}: '{stage.name}' with agent '{stage.agent}'")
                
                # Check if this is a parallel stage BEFORE creating execution record
                # Parallel stages create their own parent execution record with correct parallel_type
                is_parallel = stage.agents is not None or stage.replicas > 1
                
                # For parallel stages, skip creating stage execution here - the parallel execution method will do it
                # For non-parallel stages, create execution record now
                if not is_parallel:
                    # For resumed sessions, reuse existing stage execution ID for the paused stage
                    # For new sessions or subsequent stages, create new stage execution record
                    if i == start_from_stage and chain_context.current_stage_name:
                        # Resuming - find existing stage execution ID from history
                        stage_executions = await self.history_service.get_stage_executions(chain_context.session_id)
                        paused_stage_exec = next((s for s in stage_executions if s.stage_name == stage.name and s.status == StageStatus.PAUSED.value), None)
                        if paused_stage_exec:
                            stage_execution_id = paused_stage_exec.execution_id
                            logger.info(f"Reusing existing stage execution ID {stage_execution_id} for resumed stage '{stage.name}'")
                        else:
                            # Fallback: create new if not found (shouldn't happen)
                            logger.warning(f"Could not find paused stage execution for '{stage.name}', creating new")
                            stage_execution_id = await self.stage_manager.create_stage_execution(chain_context.session_id, stage, executed_stage_count)
                    else:
                        # Create new stage execution record
                        stage_execution_id = await self.stage_manager.create_stage_execution(chain_context.session_id, stage, executed_stage_count)
                    
                    # Update session current stage
                    await self.stage_manager.update_session_current_stage(chain_context.session_id, i, stage_execution_id)
                else:
                    # For parallel stages, the parallel executor creates and manages the parent execution record.
                    # The parent_stage_execution_id is returned in stage_result.metadata on success.
                    # On exception, parallel executor handles its own cleanup; we skip stage-level updates.
                    stage_execution_id = None
                
                try:
                    # is_parallel already checked above
                    if is_parallel:
                        # Execute parallel stage
                        logger.info(f"Stage '{stage.name}' is a parallel stage")
                        
                        # Route to appropriate parallel executor (these methods create parent execution record)
                        if stage.agents:
                            # Multi-agent parallelism
                            stage_result = await self.parallel_executor.execute_parallel_agents(
                                stage, chain_context, session_mcp_client, chain_definition, executed_stage_count
                            )
                        else:
                            # Replica parallelism (stage.replicas > 1)
                            stage_result = await self.parallel_executor.execute_replicated_agent(
                                stage, chain_context, session_mcp_client, chain_definition, executed_stage_count
                            )
                        
                        # Get parent stage execution ID from result metadata
                        parent_execution_id = (
                            stage_result.metadata.parent_stage_execution_id
                            if stage_result.metadata
                            else None
                        )
                        if not parent_execution_id:
                            raise RuntimeError(
                                f"Parallel stage '{stage.name}' returned no parent_stage_execution_id in metadata"
                            )
                        
                        # Update session current stage with parent execution ID
                        await self.stage_manager.update_session_current_stage(chain_context.session_id, i, parent_execution_id)
                        
                        # Record stage transition as interaction (non-blocking)
                        if hasattr(self.history_service, "record_session_interaction"):
                            rec = self.history_service.record_session_interaction
                            if asyncio.iscoroutinefunction(rec):
                                await rec(chain_context.session_id)
                            else:
                                await asyncio.to_thread(rec, chain_context.session_id)
                        
                        # Add parallel result to ChainContext (use parent execution_id as key)
                        chain_context.add_stage_result(parent_execution_id, stage_result)
                        
                        # Check parallel stage status
                        if stage_result.status == StageStatus.COMPLETED:
                            successful_stages += 1
                            logger.info(f"Parallel stage '{stage.name}' completed successfully")
                            
                            # ALWAYS invoke synthesis after parallel stage completion
                            logger.info(f"Invoking automatic synthesis for parallel stage '{stage.name}'")
                            try:
                                # Increment executed stage count for the parallel stage we just completed
                                executed_stage_count += 1
                                
                                # Synthesis gets the next stage index
                                synthesis_execution_id, synthesis_result = await self.parallel_executor.synthesize_parallel_results(
                                    stage_result, chain_context, session_mcp_client, stage, chain_definition, executed_stage_count
                                )
                                
                                # Add synthesized result to chain context using execution_id as key
                                # This ensures next stages receive coherent synthesized output, not raw parallel data
                                chain_context.add_stage_result(synthesis_execution_id, synthesis_result)
                                
                                # Update stage counters based on synthesis result
                                if synthesis_result.status == StageStatus.COMPLETED:
                                    successful_stages += 1
                                    executed_stage_count += 1  # Increment for the synthesis stage
                                else:
                                    failed_stages += 1
                                    logger.error(f"Synthesis for parallel stage '{stage.name}' failed")
                            except Exception as e:
                                logger.error(f"Automatic synthesis failed for parallel stage '{stage.name}': {e}", exc_info=True)
                                failed_stages += 1
                        elif stage_result.status == StageStatus.PAUSED:
                            # Parallel stage paused - propagate pause to session level
                            logger.info(f"Parallel stage '{stage.name}' paused")
                            
                            # Create pause metadata
                            pause_meta = PauseMetadata(
                                reason=PauseReason.MAX_ITERATIONS_REACHED,
                                current_iteration=0,  # Not meaningful for parallel stages
                                message=f"Parallel stage '{stage.name}' paused - one or more agents need more iterations",
                                paused_at_us=now_us()
                            )
                            
                            # Serialize pause metadata (convert enum to string)
                            pause_meta_dict = pause_meta.model_dump(mode='json')
                            
                            # Update session status to PAUSED with metadata
                            from tarsy.models.constants import AlertSessionStatus
                            self.session_manager.update_session_status(
                                chain_context.session_id, 
                                AlertSessionStatus.PAUSED.value,
                                pause_metadata=pause_meta_dict
                            )
                            
                            # Publish pause event with metadata
                            from tarsy.services.events.event_helpers import (
                                publish_session_paused,
                            )
                            await publish_session_paused(chain_context.session_id, pause_metadata=pause_meta_dict)
                            
                            # Return paused result (not failed)
                            return ChainExecutionResult(
                                status=ChainStatus.PAUSED,
                                final_analysis="Parallel stage paused - waiting for user to resume",
                                error=None,
                                timestamp_us=now_us()
                            )
                        else:
                            failed_stages += 1
                            logger.error(f"Parallel stage '{stage.name}' failed")
                    else:
                        # Single-agent execution (existing logic)
                        
                        # Record stage transition as interaction (non-blocking)
                        if hasattr(self.history_service, "record_session_interaction"):
                            rec = self.history_service.record_session_interaction
                            if asyncio.iscoroutinefunction(rec):
                                await rec(chain_context.session_id)
                            else:
                                await asyncio.to_thread(rec, chain_context.session_id)
                        
                        # Mark stage as started
                        await self.stage_manager.update_stage_execution_started(stage_execution_id)
                        
                        # Resolve effective LLM provider for this stage
                        # Precedence: stage.llm_provider > chain.llm_provider > global (None)
                        effective_provider = stage.llm_provider or chain_definition.llm_provider
                        if effective_provider:
                            logger.debug(f"Stage '{stage.name}' using LLM provider: {effective_provider}")
                        
                        # Get agent instance with stage-specific strategy and provider
                        # Pass session-scoped MCP client for isolation
                        agent = self.agent_factory.get_agent(
                            agent_identifier=stage.agent,
                            mcp_client=session_mcp_client,
                            iteration_strategy=stage.iteration_strategy,
                            llm_provider=effective_provider
                        )
                        
                        # Set current stage execution ID for interaction tagging
                        agent.set_current_stage_execution_id(stage_execution_id)
                        
                        # Update chain context for current stage
                        chain_context.current_stage_name = stage.name
                        
                        # Execute stage with ChainContext
                        logger.info(f"Executing stage '{stage.name}' with ChainContext")
                        stage_result = await agent.process_alert(chain_context)
                        
                        # Validate stage result format
                        if not isinstance(stage_result, AgentExecutionResult):
                            raise ValueError(f"Invalid stage result format from agent '{stage.agent}': expected AgentExecutionResult, got {type(stage_result)}")
                        
                        # Add stage result to ChainContext using execution_id as key
                        chain_context.add_stage_result(stage_execution_id, stage_result)
                        
                        # Check if stage actually succeeded or failed based on status
                        if stage_result.status == StageStatus.COMPLETED:
                            # Update stage execution as completed
                            await self.stage_manager.update_stage_execution_completed(stage_execution_id, stage_result)
                            successful_stages += 1
                            executed_stage_count += 1  # Increment for completed stage
                            logger.info(f"Stage '{stage.name}' completed successfully with agent '{stage_result.agent_name}'")
                        else:
                            # Stage failed - treat as failed even though no exception was thrown
                            error_msg = stage_result.error_message or f"Stage '{stage.name}' failed with status {stage_result.status.value}"
                            logger.error(f"Stage '{stage.name}' failed: {error_msg}")
                            
                            # Update stage execution as failed
                            await self.stage_manager.update_stage_execution_failed(stage_execution_id, error_msg)
                            failed_stages += 1
                    
                except asyncio.CancelledError as e:
                    # Cancellation is a normal control-flow event (user cancel, timeout, shutdown).
                    # In Python 3.13+, CancelledError derives from BaseException and will not be
                    # caught by `except Exception`.
                    reason = (
                        e.args[0]
                        if e.args and isinstance(e.args[0], str)
                        else CancellationReason.UNKNOWN.value
                    )
                    logger.info(
                        "Stage '%s' cancelled (reason=%s) in session %s",
                        stage.name,
                        reason,
                        chain_context.session_id,
                    )
                    if stage_execution_id:
                        await self.stage_manager.update_stage_execution_cancelled(
                            stage_execution_id, reason
                        )
                    raise

                except Exception as e:
                    # Check if this is a pause signal (SessionPaused)
                    if isinstance(e, SessionPaused):
                        # Session paused at max iterations - update status and exit gracefully
                        logger.info(f"Stage '{stage.name}' paused at iteration {e.iteration}")
                        
                        # Create pause metadata
                        pause_meta = PauseMetadata(
                            reason=PauseReason.MAX_ITERATIONS_REACHED,
                            current_iteration=e.iteration,
                            message=f"Paused after {e.iteration} iterations - resume to continue",
                            paused_at_us=now_us()
                        )
                        
                        # Serialize pause metadata (convert enum to string)
                        pause_meta_dict = pause_meta.model_dump(mode='json')
                        
                        # Create partial AgentExecutionResult with conversation state for resume
                        paused_result = AgentExecutionResult(
                            status=StageStatus.PAUSED,
                            agent_name=stage.agent,
                            stage_name=stage.name,
                            timestamp_us=now_us(),
                            result_summary=f"Stage '{stage.name}' paused at iteration {e.iteration}",
                            paused_conversation_state=e.conversation.model_dump() if e.conversation else None,
                            error_message=None
                        )
                        
                        # Update stage execution as paused with current iteration and conversation state
                        # Note: SessionPaused is caught by ParallelStageExecutor for parallel stages,
                        # so stage_execution_id should always be set here. Guard for safety.
                        if stage_execution_id:
                            await self.stage_manager.update_stage_execution_paused(stage_execution_id, e.iteration, paused_result)
                        
                        # Update session status to PAUSED with metadata
                        from tarsy.models.constants import AlertSessionStatus
                        self.session_manager.update_session_status(
                            chain_context.session_id, 
                            AlertSessionStatus.PAUSED.value,
                            pause_metadata=pause_meta_dict
                        )
                        
                        # Publish pause event with metadata
                        from tarsy.services.events.event_helpers import (
                            publish_session_paused,
                        )
                        await publish_session_paused(chain_context.session_id, pause_metadata=pause_meta_dict)
                        
                        # Return paused result (not failed)
                        return ChainExecutionResult(
                            status=ChainStatus.PAUSED,
                            final_analysis="Session paused - waiting for user to resume",
                            error=None,
                            timestamp_us=now_us()
                        )
                    
                    # Log the error with full context
                    error_msg = f"Stage '{stage.name}' failed with agent '{stage.agent}': {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    
                    # Update stage execution as failed (only for non-parallel stages with execution_id)
                    # Parallel stages manage their own execution records via ParallelStageExecutor
                    if stage_execution_id:
                        await self.stage_manager.update_stage_execution_failed(stage_execution_id, error_msg)
                    
                    # Add structured error as stage output for next stages
                    error_result = AgentExecutionResult(
                        status=StageStatus.FAILED,
                        agent_name=stage.agent,
                        stage_name=stage.name,
                        timestamp_us=now_us(),
                        result_summary=f"Stage '{stage.name}' failed: {str(e)}",
                        error_message=str(e),
                    )
                    if stage_execution_id:
                        chain_context.add_stage_result(stage_execution_id, error_result)
                    
                    failed_stages += 1
                    
                    # DECISION: Continue to next stage even if this one failed
                    # This allows data collection stages to fail while analysis stages still run
                    logger.warning(f"Continuing chain execution despite stage failure: {error_msg}")
            
            # Extract final analysis from stages
            final_analysis = self._extract_final_analysis_from_stages(chain_context)
            
            # Determine overall chain status and aggregate errors if any stages failed
            # Any stage failure should fail the entire session
            if failed_stages > 0:
                overall_status = ChainStatus.FAILED  # Any stage failed = session failed
                # Aggregate stage errors into meaningful chain-level error message
                chain_error = self._aggregate_stage_errors(chain_context)
                logger.error(f"Chain execution failed: {failed_stages} of {len(chain_definition.stages)} stages failed")
            else:
                overall_status = ChainStatus.COMPLETED  # All stages succeeded
                chain_error = None
                logger.info(f"Chain execution completed successfully: {successful_stages} stages completed")
            
            logger.info(f"Chain execution completed: {successful_stages} successful, {failed_stages} failed")
            
            # Set completion timestamp just before returning result
            timestamp_us = now_us()
            
            return ChainExecutionResult(
                status=overall_status,
                final_analysis=final_analysis if overall_status == ChainStatus.COMPLETED else None,
                error=chain_error if overall_status == ChainStatus.FAILED else None,
                timestamp_us=timestamp_us
            )
            
        except Exception as e:
            error_msg = f'Chain execution failed: {str(e)}'
            logger.error(error_msg)
            
            # Set completion timestamp for error case
            timestamp_us = now_us()
            
            return ChainExecutionResult(
                status=ChainStatus.FAILED,
                error=error_msg,
                timestamp_us=timestamp_us
            )
    
    def _aggregate_stage_errors(self, chain_context: ChainContext) -> str:
        """
        Aggregate error messages from failed stages into a descriptive chain-level error.
        
        Args:
            chain_context: Chain context with stage outputs and errors
            
        Returns:
            Aggregated error message describing all stage failures
        """
        error_messages = []
        
        # Collect errors from stage outputs (keys are execution_ids, extract stage_name from result)
        for stage_result in chain_context.stage_outputs.values():
            if hasattr(stage_result, 'status') and stage_result.status == StageStatus.FAILED:
                stage_name = getattr(stage_result, 'stage_name', 'unknown')
                stage_agent = getattr(stage_result, 'agent_name', 'unknown')
                stage_error = getattr(stage_result, 'error_message', None)
                
                if stage_error:
                    error_messages.append(f"Stage '{stage_name}' (agent: {stage_agent}): {stage_error}")
                else:
                    error_messages.append(f"Stage '{stage_name}' (agent: {stage_agent}): Failed with no error message")
        
        # If we have specific error messages, format them nicely
        if error_messages:
            if len(error_messages) == 1:
                return f"Chain processing failed: {error_messages[0]}"
            else:
                numbered_errors = [f"{i+1}. {msg}" for i, msg in enumerate(error_messages)]
                return f"Chain processing failed with {len(error_messages)} stage failures:\n" + "\n".join(numbered_errors)
        
        # Fallback if no specific errors found
        return "Chain processing failed: One or more stages failed without detailed error messages"

    def _extract_final_analysis_from_stages(self, chain_context: ChainContext) -> str:
        """
        Extract final analysis from stages for API consumption.
        
        Uses the final_analysis field which contains clean, concise summaries
        extracted by each agent's iteration controller.
        """
        # Look for final_analysis from the last successful stage (typically a final-analysis stage)
        for stage_name in reversed(list(chain_context.stage_outputs.keys())):
            stage_result = chain_context.stage_outputs[stage_name]
            if isinstance(stage_result, AgentExecutionResult) and stage_result.status == StageStatus.COMPLETED and stage_result.final_analysis:
                return stage_result.final_analysis
        
        # Fallback: look for any final_analysis from any successful stage
        for stage_result in chain_context.stage_outputs.values():
            if isinstance(stage_result, AgentExecutionResult) and stage_result.status == StageStatus.COMPLETED and stage_result.final_analysis:
                return stage_result.final_analysis
        
        # If no analysis found, return a simple summary (this should be rare)
        return f"Chain {chain_context.chain_id} completed with {len(chain_context.stage_outputs)} stage outputs."

    async def close(self):
        """
        Clean up resources.
        """
        import asyncio
        try:
            # Safely close runbook service (handle both sync and async close methods)
            if hasattr(self.runbook_service, 'close'):
                result = self.runbook_service.close()
                if asyncio.iscoroutine(result):
                    await result
            
            # Safely close health check MCP client (handle both sync and async close methods)
            if hasattr(self.health_check_mcp_client, 'close'):
                result = self.health_check_mcp_client.close()
                if asyncio.iscoroutine(result):
                    await result
            
            logger.info("AlertService resources cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")


def get_alert_service() -> Optional[AlertService]:
    """
    Get the global alert service instance.
    
    Returns:
        AlertService instance or None if not initialized
    """
    from tarsy.main import alert_service
    return alert_service
