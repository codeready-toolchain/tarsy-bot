"""
Alert Service for multi-layer agent architecture.

This module provides the service that delegates alert processing to
specialized agents based on alert type. It implements the multi-layer
agent architecture for alert processing.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import asyncio
from typing import Any, Dict, Optional

import httpx

from tarsy.agents.exceptions import SessionPaused
from tarsy.config.agent_config import ConfigurationError, ConfigurationLoader
from tarsy.config.settings import Settings
from tarsy.integrations.llm.manager import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.integrations.notifications.summarizer import ExecutiveSummaryAgent
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel, ParallelAgentConfig
from tarsy.models.agent_execution_result import AgentExecutionResult, ParallelStageResult
from tarsy.models.api_models import ChainExecutionResult
from tarsy.models.constants import (
    AlertSessionStatus,
    ChainStatus,
    FailurePolicy,
    ParallelType,
    StageStatus,
)
from tarsy.models.db_models import StageExecution
from tarsy.models.pause_metadata import PauseMetadata, PauseReason
from tarsy.models.processing_context import ChainContext
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.chain_registry import ChainRegistry
from tarsy.services.history_service import get_history_service
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.runbook_service import RunbookService
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

logger = get_module_logger(__name__)


# ============================================================================
# API Formatting Functions
# These functions format alert data for API responses only
# ============================================================================

def _format_alert_severity(alert_data: Dict[str, Any]) -> str:
    """Format alert severity for API responses."""
    return alert_data.get('severity', 'warning')


def _format_alert_environment(alert_data: Dict[str, Any]) -> str:
    """Format alert environment for API responses."""
    return alert_data.get('environment', 'production')


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
        
        # Initialize agent factory with dependencies (no MCP client - provided per agent)
        self.agent_factory = None  # Will be initialized in initialize()
        
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
                self._update_session_error(chain_context.session_id, error_msg)
                    
                return self._format_error_response(chain_context, error_msg)
            
            logger.info(f"Selected chain '{chain_definition.chain_id}' for alert type '{chain_context.processing_alert.alert_type}'")
            
            # Create history session with chain info
            session_created = self._create_chain_history_session(chain_context, chain_definition)
            
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
            self._update_session_status(chain_context.session_id, AlertSessionStatus.IN_PROGRESS.value)
            
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
            
            # Step 6: Execute chain stages sequentially with 600s overall timeout
            try:
                chain_result = await asyncio.wait_for(
                    self._execute_chain_stages(
                        chain_definition=chain_definition,
                        chain_context=chain_context,
                        session_mcp_client=session_mcp_client
                    ),
                    timeout=600.0  # 10 minute overall session limit
                )
            except asyncio.TimeoutError:
                error_msg = "Alert processing exceeded 600s overall timeout"
                logger.error(f"{error_msg} for session {chain_context.session_id}")
                # Update history session with timeout error
                self._update_session_error(chain_context.session_id, error_msg)
                # Publish session.failed event
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(chain_context.session_id)
                return self._format_error_response(chain_context, error_msg)
            
            # Step 7: Format and return results
            if chain_result.status == ChainStatus.COMPLETED:
                analysis = chain_result.final_analysis or 'No analysis provided'
                
                # Format final result with chain context
                final_result = self._format_chain_success_response(
                    chain_context,
                    chain_definition,
                    analysis,
                    chain_result.timestamp_us
                )
                
                # Generate executive summary for dashboard display and external notifications
                # Use chain-level provider for executive summary (or global if not set)
                final_result_summary = await self.final_analysis_summarizer.generate_executive_summary(
                    content=analysis,
                    session_id=chain_context.session_id,
                    provider=chain_definition.llm_provider
                )

                # Mark history session as completed successfully
                self._update_session_status(
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
                return self._format_chain_success_response(
                    chain_context,
                    chain_definition,
                    chain_result.final_analysis,
                    chain_result.timestamp_us
                )
            else:
                # Handle chain processing error
                error_msg = chain_result.error or 'Chain processing failed'
                logger.error(f"Chain processing failed: {error_msg}")
                
                # Update history session with processing error
                self._update_session_error(chain_context.session_id, error_msg)
                
                # Publish session.failed event
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(chain_context.session_id)
                
                return self._format_error_response(chain_context, error_msg)
                
        except Exception as e:
            error_msg = f"Alert processing failed: {str(e)}"
            logger.error(error_msg)
            
            # Update history session with processing error
            self._update_session_error(chain_context.session_id, error_msg)
            
            # Publish session.failed event
            from tarsy.services.events.event_helpers import publish_session_failed
            await publish_session_failed(chain_context.session_id)
            
            return self._format_error_response(chain_context, error_msg)
        
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
            
            # Step 3: Reconstruct ChainContext from session data
            from tarsy.models.alert import ProcessingAlert
            
            # Reconstruct ProcessingAlert from session fields
            # Note: session.alert_data only contains the nested alert dict, not the full ProcessingAlert
            processing_alert = ProcessingAlert(
                alert_type=session.alert_type or "unknown",
                severity=session.alert_data.get("severity", "warning"),  # Extract from alert_data or use default
                timestamp=session.started_at_us,
                environment=session.alert_data.get("environment", "production"),
                runbook_url=session.runbook_url,
                alert_data=session.alert_data
            )
            
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id=session_id,
                current_stage_name=paused_stage.stage_name,
                author=session.author
            )
            
            # Restore MCP selection if it was present
            if session.mcp_selection:
                from tarsy.models.mcp_selection_models import MCPSelectionConfig
                chain_context.mcp = MCPSelectionConfig.model_validate(session.mcp_selection)
            
            # Reconstruct stage outputs from completed AND paused stages
            # IMPORTANT: Paused stages need their conversation history restored
            # NOTE: Parallel stages have ParallelStageResult, not AgentExecutionResult
            for stage_exec in stage_executions:
                if stage_exec.status == StageStatus.COMPLETED.value and stage_exec.stage_output:
                    # Check if this is a parallel stage (parent execution)
                    if stage_exec.parallel_type in ParallelType.parallel_values():
                        # Reconstruct ParallelStageResult from stage_output
                        from tarsy.models.agent_execution_result import ParallelStageResult
                        result = ParallelStageResult.model_validate(stage_exec.stage_output)
                    else:
                        # Reconstruct AgentExecutionResult from stage_output
                        result = AgentExecutionResult.model_validate(stage_exec.stage_output)
                    chain_context.add_stage_result(stage_exec.stage_name, result)
                elif stage_exec.status == StageStatus.PAUSED.value and stage_exec.stage_output:
                    # Check if this is a parallel stage (parent execution)
                    if stage_exec.parallel_type in ParallelType.parallel_values():
                        # Restore paused parallel stage's result for resume
                        from tarsy.models.agent_execution_result import ParallelStageResult
                        result = ParallelStageResult.model_validate(stage_exec.stage_output)
                    else:
                        # Restore paused stage's conversation history for resume
                        result = AgentExecutionResult.model_validate(stage_exec.stage_output)
                    chain_context.add_stage_result(stage_exec.stage_name, result)
                    logger.info(f"Restored conversation history for paused stage '{stage_exec.stage_name}'")
            
            # Step 4: Get chain definition
            chain_definition = session.chain_config
            if not chain_definition:
                raise Exception("Chain definition not found in session")
            
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
            self._update_session_status(session_id, AlertSessionStatus.IN_PROGRESS.value)
            
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
                parallel_result = await self._resume_parallel_stage(
                    paused_parent_stage=paused_stage,
                    chain_context=chain_context,
                    session_mcp_client=session_mcp_client,
                    chain_definition=chain_definition,
                    stage_index=stage_index
                )
                
                # Add result to context
                chain_context.add_stage_result(paused_stage.stage_name, parallel_result)
                
                # Check if we need to continue to next stages
                if parallel_result.status == StageStatus.COMPLETED:
                    # Continue with remaining stages
                    result = await self._execute_chain_stages(
                        chain_definition,
                        chain_context,
                        session_mcp_client
                    )
                elif parallel_result.status == StageStatus.PAUSED:
                    # Paused again - return pause result
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
                final_result = self._format_chain_success_response(
                    chain_context,
                    chain_definition,
                    analysis,
                    result.timestamp_us,
                )
                
                # Generate executive summary for resumed sessions too
                # Use chain-level provider for executive summary (or global if not set)
                final_result_summary = await self.final_analysis_summarizer.generate_executive_summary(
                    content=analysis,
                    session_id=session_id,
                    provider=chain_definition.llm_provider
                )
                
                self._update_session_status(
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
                # Status already updated to PAUSED and pause event already published in _execute_chain_stages
                logger.info(f"Resumed session {session_id} paused again (hit max iterations)")
                # Format the pause message consistently with initial execution path
                pause_message = result.final_analysis or "Session paused again - waiting for user to resume"
                return self._format_chain_success_response(
                    chain_context,
                    chain_definition,
                    pause_message,
                    result.timestamp_us,
                )
            else:
                error_msg = result.error or "Chain execution failed"
                self._update_session_status(session_id, AlertSessionStatus.FAILED.value)
                from tarsy.services.events.event_helpers import publish_session_failed
                await publish_session_failed(session_id)
                return self._format_error_response(chain_context, error_msg)
        
        except Exception as e:
            error_msg = f"Failed to resume session: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._update_session_error(session_id, error_msg)
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
                            stage_execution_id = await self._create_stage_execution(chain_context.session_id, stage, i)
                    else:
                        # Create new stage execution record
                        stage_execution_id = await self._create_stage_execution(chain_context.session_id, stage, i)
                    
                    # Update session current stage
                    await self._update_session_current_stage(chain_context.session_id, i, stage_execution_id)
                else:
                    # For parallel stages, we'll update session current stage after parallel execution completes
                    stage_execution_id = None  # Will be set by parallel execution method
                
                try:
                    # is_parallel already checked above
                    if is_parallel:
                        # Execute parallel stage
                        logger.info(f"Stage '{stage.name}' is a parallel stage")
                        
                        # Route to appropriate parallel executor (these methods create parent execution record)
                        if stage.agents:
                            # Multi-agent parallelism
                            stage_result = await self._execute_parallel_agents(
                                stage, chain_context, session_mcp_client, chain_definition, i
                            )
                        else:
                            # Replica parallelism (stage.replicas > 1)
                            stage_result = await self._execute_replicated_agent(
                                stage, chain_context, session_mcp_client, chain_definition, i
                            )
                        
                        # Get parent stage execution ID from result metadata
                        parent_execution_id = stage_result.metadata.parent_stage_execution_id if stage_result.metadata else None
                        
                        # Update session current stage with parent execution ID
                        if parent_execution_id:
                            await self._update_session_current_stage(chain_context.session_id, i, parent_execution_id)
                        
                        # Record stage transition as interaction (non-blocking)
                        if self.history_service and hasattr(self.history_service, "record_session_interaction"):
                            rec = self.history_service.record_session_interaction
                            if asyncio.iscoroutinefunction(rec):
                                await rec(chain_context.session_id)
                            else:
                                await asyncio.to_thread(rec, chain_context.session_id)
                        
                        # Add parallel result to ChainContext
                        chain_context.add_stage_result(stage.name, stage_result)
                        
                        # Check parallel stage status
                        if stage_result.status == StageStatus.COMPLETED:
                            successful_stages += 1
                            logger.info(f"Parallel stage '{stage.name}' completed successfully")
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
                            self._update_session_status(
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
                        if self.history_service and hasattr(self.history_service, "record_session_interaction"):
                            rec = self.history_service.record_session_interaction
                            if asyncio.iscoroutinefunction(rec):
                                await rec(chain_context.session_id)
                            else:
                                await asyncio.to_thread(rec, chain_context.session_id)
                        
                        # Mark stage as started
                        await self._update_stage_execution_started(stage_execution_id)
                        
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
                        
                        # Add stage result to ChainContext
                        chain_context.add_stage_result(stage.name, stage_result)
                        
                        # Check if stage actually succeeded or failed based on status
                        if stage_result.status == StageStatus.COMPLETED:
                            # Update stage execution as completed
                            await self._update_stage_execution_completed(stage_execution_id, stage_result)
                            successful_stages += 1
                            logger.info(f"Stage '{stage.name}' completed successfully with agent '{stage_result.agent_name}'")
                        else:
                            # Stage failed - treat as failed even though no exception was thrown
                            error_msg = stage_result.error_message or f"Stage '{stage.name}' failed with status {stage_result.status.value}"
                            logger.error(f"Stage '{stage.name}' failed: {error_msg}")
                            
                            # Update stage execution as failed
                            await self._update_stage_execution_failed(stage_execution_id, error_msg)
                            failed_stages += 1
                    
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
                        await self._update_stage_execution_paused(stage_execution_id, e.iteration, paused_result)
                        
                        # Update session status to PAUSED with metadata
                        from tarsy.models.constants import AlertSessionStatus
                        self._update_session_status(
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
                    
                    # Update stage execution as failed
                    await self._update_stage_execution_failed(stage_execution_id, error_msg)
                    
                    # Add structured error as stage output for next stages
                    error_result = AgentExecutionResult(
                        status=StageStatus.FAILED,
                        agent_name=stage.agent,
                        stage_name=stage.name,
                        timestamp_us=now_us(),
                        result_summary=f"Stage '{stage.name}' failed: {str(e)}",
                        error_message=str(e),
                    )
                    chain_context.add_stage_result(stage.name, error_result)
                    
                    failed_stages += 1
                    
                    # DECISION: Continue to next stage even if this one failed
                    # This allows data collection stages to fail while analysis stages still run
                    logger.warning(f"Continuing chain execution despite stage failure: {error_msg}")
            
            # Check if we need automatic synthesis for final parallel stage
            if self._is_final_stage_parallel(chain_definition):
                from tarsy.models.agent_execution_result import ParallelStageResult
                
                last_result = chain_context.get_last_stage_result()
                if isinstance(last_result, ParallelStageResult):
                    logger.info("Final stage is parallel - invoking automatic SynthesisAgent synthesis")
                    try:
                        synthesis_result = await self._synthesize_parallel_results(
                            last_result, chain_context, session_mcp_client, chain_definition
                        )
                        # Add synthesis result as final stage
                        chain_context.add_stage_result("synthesis", synthesis_result)
                        
                        # Update stage counters based on synthesis result
                        if synthesis_result.status == StageStatus.COMPLETED:
                            successful_stages += 1
                        else:
                            failed_stages += 1
                    except Exception as e:
                        logger.error(f"Automatic synthesis failed: {e}", exc_info=True)
                        failed_stages += 1
            
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
        
        # Collect errors from stage outputs
        for stage_name, stage_result in chain_context.stage_outputs.items():
            if hasattr(stage_result, 'status') and stage_result.status == StageStatus.FAILED:
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

    def _format_success_response(
        self,
        chain_context: ChainContext,
        agent_name: str,
        analysis: str,
        iterations: int,
        timestamp_us: Optional[int] = None
    ) -> str:
        """
        Format successful analysis response for alert data.
        
        Args:
            chain_context: The alert processing data with validated structure
            agent_name: Name of the agent that processed the alert
            analysis: Analysis result from the agent
            iterations: Number of iterations performed
            timestamp_us: Processing timestamp in microseconds since epoch UTC
            
        Returns:
            Formatted response string
        """
        # Convert unix timestamp to string for display
        if timestamp_us:
            timestamp_str = f"{timestamp_us}"  # Keep as unix timestamp for consistency
        else:
            timestamp_str = f"{now_us()}"  # Current unix timestamp
        
        response_parts = [
            "# Alert Analysis Report",
            "",
            f"**Alert Type:** {chain_context.processing_alert.alert_type}",
            f"**Processing Agent:** {agent_name}",
            f"**Environment:** {_format_alert_environment(chain_context.processing_alert.alert_data)}",
            f"**Severity:** {_format_alert_severity(chain_context.processing_alert.alert_data)}",
            f"**Timestamp:** {timestamp_str}",
            "",
            "## Analysis",
            "",
            analysis,
            "",
            "---",
            f"*Processed by {agent_name} in {iterations} iterations*"
        ]
        
        return "\n".join(response_parts)
    
    def _format_chain_success_response(
        self,
        chain_context: ChainContext,
        chain_definition,
        analysis: str,
        timestamp_us: Optional[int] = None
    ) -> str:
        """
        Format successful analysis response for chain processing.
        
        Args:
            chain_context: The alert processing data with validated structure
            chain_definition: Chain definition that was executed
            analysis: Combined analysis result from all stages
            timestamp_us: Processing timestamp in microseconds since epoch UTC
            
        Returns:
            Formatted response string
        """
        # Convert unix timestamp to string for display
        if timestamp_us:
            timestamp_str = f"{timestamp_us}"  # Keep as unix timestamp for consistency
        else:
            timestamp_str = f"{now_us()}"  # Current unix timestamp
        
        response_parts = [
            "# Alert Analysis Report",
            "",
            f"**Alert Type:** {chain_context.processing_alert.alert_type}",
            f"**Processing Chain:** {chain_definition.chain_id}",
            f"**Stages:** {len(chain_definition.stages)}",
            f"**Environment:** {_format_alert_environment(chain_context.processing_alert.alert_data)}",
            f"**Severity:** {_format_alert_severity(chain_context.processing_alert.alert_data)}",
            f"**Timestamp:** {timestamp_str}",
            "",
            "## Analysis",
            "",
            analysis,
            "",
            "---",
            f"*Processed through {len(chain_definition.stages)} stages*"
        ]
        
        return "\n".join(response_parts)
    
    def _format_error_response(
        self,
        chain_context: ChainContext,
        error: str,
        agent_name: Optional[str] = None
    ) -> str:
        """
        Format error response for alert data.
        
        Args:
            chain_context: The alert processing data with validated structure
            error: Error message
            agent_name: Name of the agent if known
            
        Returns:
            Formatted error response string
        """
        response_parts = [
            "# Alert Processing Error",
            "",
            f"**Alert Type:** {chain_context.processing_alert.alert_type}",
            f"**Environment:** {_format_alert_environment(chain_context.processing_alert.alert_data)}",
            f"**Error:** {error}",
        ]
        
        if agent_name:
            response_parts.append(f"**Failed Agent:** {agent_name}")
        
        response_parts.extend([
            "",
            "## Troubleshooting",
            "",
            "1. Check that the alert type is supported",
            "2. Verify agent configuration in settings",
            "3. Ensure all required services are available",
            "4. Review logs for detailed error information"
        ])
        
        return "\n".join(response_parts)

    # History Session Management Methods

    def _create_chain_history_session(self, chain_context: ChainContext, chain_definition: ChainConfigModel) -> bool:
        """
        Create a history session for chain processing.
        
        Args:
            chain_context: Chain context with all processing data
            chain_definition: Chain definition that will be executed
            
        Returns:
            True if created successfully, False if history service unavailable or creation failed
        """
        try:
            if not self.history_service or not self.history_service.is_enabled:
                return False
            
            # Store chain information in session using ChainContext and ChainDefinition
            created_successfully = self.history_service.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            
            if created_successfully:
                logger.info(f"Created chain history session {chain_context.session_id} with chain {chain_definition.chain_id}")
                return True
            else:
                logger.warning(f"Failed to create chain history session {chain_context.session_id} with chain {chain_definition.chain_id}")
                return False
            
        except Exception as e:
            logger.warning(f"Failed to create chain history session: {str(e)}")
            return False
    
    def _update_session_status(
        self, 
        session_id: Optional[str], 
        status: str,
        error_message: Optional[str] = None,
        final_analysis: Optional[str] = None,
        final_analysis_summary: Optional[str] = None,
        pause_metadata: Optional[dict] = None
    ):
        """
        Update history session status.
        
        Args:
            session_id: Session ID to update
            status: New status
            error_message: Optional error message if failed
            final_analysis: Optional final analysis if completed
            pause_metadata: Optional pause metadata if paused
        """
        try:
            if not session_id or not self.history_service or not self.history_service.is_enabled:
                return
                
            self.history_service.update_session_status(
                session_id=session_id,
                status=status,
                error_message=error_message,
                final_analysis=final_analysis,
                final_analysis_summary=final_analysis_summary,
                pause_metadata=pause_metadata
            )
            
        except Exception as e:
            logger.warning(f"Failed to update session status: {str(e)}")
    
    
    def _update_session_error(self, session_id: Optional[str], error_message: str):
        """
        Mark history session as failed with error.
        
        Args:
            session_id: Session ID to update
            error_message: Error message
        """
        try:
            if not session_id or not self.history_service or not self.history_service.is_enabled:
                return
                
            # Status 'failed' will automatically set completed_at_us in the history service
            self.history_service.update_session_status(
                session_id=session_id,
                status=AlertSessionStatus.FAILED.value,
                error_message=error_message
            )
            
        except Exception as e:
            logger.warning(f"Failed to update session error: {str(e)}")
    
    def clear_caches(self):
        """
        Clear all alert-related caches.
        
        Note: This method is now a no-op as in-memory caches have been removed.
        Kept for backwards compatibility.
        """
        logger.debug("clear_caches called (no-op, caches removed)")
    
    # Stage execution helper methods
    async def _create_stage_execution(
        self,
        session_id: str,
        stage,
        stage_index: int,
        parent_stage_execution_id: Optional[str] = None,
        parallel_index: int = 0,
        parallel_type: str = ParallelType.SINGLE.value,
    ) -> str:
        """
        Create a stage execution record with optional parallel execution tracking.
        
        Args:
            session_id: Session ID
            stage: Stage definition
            stage_index: Stage index in chain
            parent_stage_execution_id: Parent stage execution ID for parallel child stages
            parallel_index: Position in parallel group (0 for single/parent, 1-N for children)
            parallel_type: Execution type (ParallelType.SINGLE, MULTI_AGENT, or REPLICA)
            
        Returns:
            Stage execution ID
            
        Raises:
            RuntimeError: If stage execution record cannot be created
        """
        if not self.history_service or not self.history_service.is_enabled:
            raise RuntimeError(
                f"Cannot create stage execution for '{stage.name}': History service is disabled. "
                "All alert processing must be done as chains with proper stage tracking."
            )
        
        from tarsy.models.db_models import StageExecution
        stage_execution = StageExecution(
            session_id=session_id,
            stage_id=f"{stage.name}_{stage_index}",
            stage_index=stage_index,
            stage_name=stage.name,
            agent=stage.agent,
            status=StageStatus.PENDING.value,
            parent_stage_execution_id=parent_stage_execution_id,
            parallel_index=parallel_index,
            parallel_type=parallel_type,
        )
        
        # Trigger stage execution hooks (history + dashboard) via context manager
        try:
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(session_id, stage_execution):
                # Context automatically triggers hooks when exiting
                # History hook will create DB record and set execution_id on the model
                pass
            logger.debug(f"Successfully triggered hooks for stage execution {stage_index}: {stage.name}")
        except Exception as e:
            logger.error(f"Critical failure creating stage execution for '{stage.name}': {str(e)}")
            raise RuntimeError(
                f"Failed to create stage execution record for stage '{stage.name}' (index {stage_index}). "
                f"Chain processing cannot continue without proper stage tracking. Error: {str(e)}"
            ) from e
        
        # Verify the execution_id was properly set by the history hook
        if not hasattr(stage_execution, 'execution_id') or not stage_execution.execution_id:
            raise RuntimeError(
                f"Stage execution record for '{stage.name}' was created but execution_id is missing. "
                "This indicates a critical bug in the history service or database layer."
            )
        
        # CRITICAL: Verify the stage execution was actually created in the database
        # The hooks use safe_execute which catches exceptions and returns False instead of propagating
        # We need to explicitly verify the record exists in the database
        if self.history_service:
            try:
                # Query the database to confirm the record exists
                from tarsy.models.db_models import StageExecution as DBStageExecution
                def _verify_stage_operation():
                    with self.history_service.get_repository() as repo:
                        if repo:
                            return repo.session.get(DBStageExecution, stage_execution.execution_id) is not None
                        return False
                
                exists = await self.history_service._retry_database_operation_async(
                    "verify_stage_execution",
                    _verify_stage_operation,
                    treat_none_as_success=False
                )
                
                if not exists:
                    raise RuntimeError(
                        f"Stage execution {stage_execution.execution_id} for '{stage.name}' was not found in database after creation. "
                        "The history hook may have failed silently. Check history service logs for errors."
                    )
                    
                logger.debug(f"Verified stage execution {stage_execution.execution_id} exists in database")
                
            except Exception as e:
                logger.error(f"Failed to verify stage execution in database: {e}")
                raise RuntimeError(
                    f"Cannot verify stage execution {stage_execution.execution_id} was created in database. "
                    f"Chain processing cannot continue without confirmation. Error: {str(e)}"
                ) from e
        
        return stage_execution.execution_id
    
    async def _update_session_current_stage(self, session_id: str, stage_index: int, stage_execution_id: str):
        """
        Update the current stage information for a session.
        
        Args:
            session_id: Session ID
            stage_index: Current stage index
            stage_execution_id: Current stage execution ID
        """
        try:
            if not self.history_service or not self.history_service.is_enabled:
                return
            
            await self.history_service.update_session_current_stage(
                session_id=session_id,
                current_stage_index=stage_index,
                current_stage_id=stage_execution_id
            )
            
        except Exception as e:
            logger.warning(f"Failed to update session current stage: {str(e)}")
    
    async def _update_stage_execution_completed(self, stage_execution_id: str, stage_result: AgentExecutionResult):
        """
        Update stage execution as completed.
        
        Args:
            stage_execution_id: Stage execution ID
            stage_result: Stage processing result
        """
        try:
            if not self.history_service:
                return
            
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update only the completion-related fields
            existing_stage.status = stage_result.status.value
            existing_stage.completed_at_us = stage_result.timestamp_us
            # Serialize AgentExecutionResult to JSON-compatible dict for database storage
            existing_stage.stage_output = stage_result.model_dump(mode='json')
            existing_stage.error_message = None
            
            # Calculate duration if we have started_at_us
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int((existing_stage.completed_at_us - existing_stage.started_at_us) / 1000)
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            try:
                from tarsy.hooks.hook_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage):
                    # Context automatically triggers hooks when exiting
                    pass
                logger.debug(f"Triggered stage hooks for stage completion {existing_stage.stage_index}: {existing_stage.stage_id}")
            except Exception as e:
                logger.warning(f"Failed to trigger stage completion hooks: {str(e)}")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as completed: {str(e)}")
    
    async def _update_stage_execution_failed(self, stage_execution_id: str, error_message: str):
        """
        Update stage execution as failed.
        
        Args:
            stage_execution_id: Stage execution ID
            error_message: Error message
        """
        try:
            if not self.history_service:
                return
            
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update only the failure-related fields
            existing_stage.status = StageStatus.FAILED.value
            existing_stage.completed_at_us = now_us()
            existing_stage.stage_output = None
            existing_stage.error_message = error_message
            
            # Calculate duration if we have started_at_us
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int((existing_stage.completed_at_us - existing_stage.started_at_us) / 1000)
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            try:
                from tarsy.hooks.hook_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage):
                    # Context automatically triggers hooks when exiting
                    pass
                logger.debug(f"Triggered stage hooks for stage failure {existing_stage.stage_index}: {existing_stage.stage_id}")
            except Exception as e:
                logger.warning(f"Failed to trigger stage failure hooks: {str(e)}")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as failed: {str(e)}")
    
    async def _update_stage_execution_paused(
        self, 
        stage_execution_id: str, 
        iteration: int, 
        paused_result: Optional[AgentExecutionResult] = None
    ):
        """
        Update stage execution as paused.
        
        Args:
            stage_execution_id: Stage execution ID
            iteration: Current iteration number when paused
            paused_result: Optional partial AgentExecutionResult with conversation history
        """
        try:
            if not self.history_service:
                return
            
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update to paused status with iteration count
            existing_stage.status = StageStatus.PAUSED.value
            existing_stage.current_iteration = iteration
            # Don't set completed_at_us - stage is not complete
            # IMPORTANT: Save conversation state so resume can continue from where it left off
            if paused_result:
                existing_stage.stage_output = paused_result.model_dump(mode='json')
                logger.info(f"Saved conversation state for paused stage {existing_stage.stage_name}")
            else:
                existing_stage.stage_output = None
            existing_stage.error_message = None
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            try:
                from tarsy.hooks.hook_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage):
                    # Context automatically triggers hooks when exiting
                    pass
                logger.debug(f"Triggered stage hooks for stage pause {existing_stage.stage_index}: {existing_stage.stage_id}")
            except Exception as e:
                logger.warning(f"Failed to trigger stage pause hooks: {str(e)}")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as paused: {str(e)}")
    
    async def _update_stage_execution_started(self, stage_execution_id: str):
        """
        Update stage execution as started.
        
        Handles PAUSED→ACTIVE transition for resumed sessions and initial PENDING→ACTIVE
        transition for new stages. Clears current_iteration for both cases to ensure
        consistent state management.
        
        Args:
            stage_execution_id: Stage execution ID
        """
        try:
            if not self.history_service:
                return
            
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update to active status and set start time
            # This handles both PENDING→ACTIVE (new) and PAUSED→ACTIVE (resumed)
            existing_stage.status = StageStatus.ACTIVE.value
            existing_stage.started_at_us = now_us()
            # Clear current_iteration for both new and resumed executions
            # Agent will set this during execution
            existing_stage.current_iteration = None
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            try:
                from tarsy.hooks.hook_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage):
                    # Context automatically triggers hooks when exiting
                    # History hook will update DB record and dashboard hook will broadcast
                    pass
                logger.debug(f"Triggered stage hooks for stage start {existing_stage.stage_index}: {existing_stage.stage_id}")
            except Exception as e:
                logger.warning(f"Failed to trigger stage start hooks: {str(e)}")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as started: {str(e)}")
    
    async def _execute_parallel_agents(
        self,
        stage: "ChainStageConfigModel",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel",
        stage_index: int
    ) -> ParallelStageResult:
        """Execute multiple different agents in parallel for independent domain investigation."""
        from tarsy.models.agent_execution_result import ParallelStageResult
        
        logger.info(f"Executing parallel stage '{stage.name}' with {len(stage.agents)} agents")
        
        # Build execution configs for each agent
        execution_configs = [
            {
                "agent_name": agent_config.name,
                "llm_provider": agent_config.llm_provider or stage.llm_provider or chain_definition.llm_provider,
                "iteration_strategy": agent_config.iteration_strategy,
            }
            for agent_config in stage.agents
        ]
        
        return await self._execute_parallel_stage(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=session_mcp_client,
            chain_definition=chain_definition,
            stage_index=stage_index,
            execution_configs=execution_configs,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
    
    async def _execute_replicated_agent(
        self,
        stage: "ChainStageConfigModel",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel",
        stage_index: int
    ) -> ParallelStageResult:
        """Run same agent N times with identical configuration for accuracy via redundancy."""
        from tarsy.models.agent_execution_result import ParallelStageResult
        
        logger.info(f"Executing replicated stage '{stage.name}' with {stage.replicas} replicas of agent '{stage.agent}'")
        
        # Resolve stage-level provider and strategy (same for all replicas)
        effective_provider = stage.llm_provider or chain_definition.llm_provider
        effective_strategy = stage.iteration_strategy
        
        # Build execution configs for each replica
        execution_configs = [
            {
                "agent_name": f"{stage.agent}-{idx + 1}",  # Replica naming
                "base_agent_name": stage.agent,  # Original agent name
                "llm_provider": effective_provider,
                "iteration_strategy": effective_strategy,
            }
            for idx in range(stage.replicas)
        ]
        
        return await self._execute_parallel_stage(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=session_mcp_client,
            chain_definition=chain_definition,
            stage_index=stage_index,
            execution_configs=execution_configs,
            parallel_type=ParallelType.REPLICA.value
        )
    
    async def _execute_parallel_stage(
        self,
        stage: "ChainStageConfigModel",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel",
        stage_index: int,
        execution_configs: list,
        parallel_type: str
    ) -> ParallelStageResult:
        """
        Common execution logic for parallel stages (multi-agent or replica).
        
        Args:
            stage: Stage configuration
            chain_context: Chain context for this session
            session_mcp_client: Session-scoped MCP client
            chain_definition: Full chain definition
            stage_index: Index of this stage in the chain
            execution_configs: List of dicts with agent_name, llm_provider, iteration_strategy (and optionally base_agent_name)
            parallel_type: "multi_agent" or "replica"
            
        Returns:
            ParallelStageResult with aggregated results and metadata
        """
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            ParallelStageMetadata,
            ParallelStageResult,
        )
        
        stage_started_at_us = now_us()
        
        # Create a synthetic stage object for parent stage creation
        # Parent stages need an agent value for the database schema (NOT NULL constraint)
        from types import SimpleNamespace
        parent_stage = SimpleNamespace(
            name=stage.name,
            agent=f"parallel-{parallel_type}"  # Synthetic agent name for parent record
        )
        
        # Create parent stage execution record with parallel_type
        parent_stage_execution_id = await self._create_stage_execution(
            chain_context.session_id,
            parent_stage,
            stage_index,
            parent_stage_execution_id=None,  # This is the parent
            parallel_index=0,  # Parent is always index 0
            parallel_type=parallel_type,  # "multi_agent" or "replica"
        )
        await self._update_stage_execution_started(parent_stage_execution_id)
        
        # Prepare parallel executions
        async def execute_single(config: dict, idx: int):
            """Execute a single agent/replica and return (result, metadata) tuple."""
            agent_started_at_us = now_us()
            agent_name = config["agent_name"]
            base_agent = config.get("base_agent_name", agent_name)  # For replicas
            
            # Create a mock stage object for child stage creation
            from types import SimpleNamespace
            child_stage = SimpleNamespace(
                name=f"{stage.name} - {agent_name}",
                agent=agent_name
            )
            
            # Create child stage execution record
            child_execution_id = await self._create_stage_execution(
                session_id=chain_context.session_id,
                stage=child_stage,
                stage_index=stage_index,
                parent_stage_execution_id=parent_stage_execution_id,
                parallel_index=idx + 1,  # 1-based indexing for children
                parallel_type=parallel_type,
            )
            # Fire-and-forget the status update to avoid SQLite write serialization
            # This prevents parallel agents from blocking each other on database writes
            asyncio.create_task(self._update_stage_execution_started(child_execution_id))
            
            try:
                logger.debug(f"Executing {parallel_type} {idx+1}/{len(execution_configs)}: '{agent_name}'")
                
                # Get agent instance from factory
                agent = self.agent_factory.get_agent(
                    agent_identifier=base_agent,
                    mcp_client=session_mcp_client,
                    iteration_strategy=config.get("iteration_strategy"),
                    llm_provider=config.get("llm_provider")
                )
                
                # Set current stage execution ID for interaction tagging (hooks need this!)
                agent.set_current_stage_execution_id(child_execution_id)
                
                # Execute agent
                result = await agent.process_alert(chain_context)
                
                # Override agent_name for replicas
                if parallel_type == "replica":
                    result.agent_name = agent_name
                
                # Update child stage execution with result based on status
                if result.status == StageStatus.COMPLETED:
                    await self._update_stage_execution_completed(child_execution_id, result)
                elif result.status == StageStatus.PAUSED:
                    # Agent paused normally (not via exception) - this shouldn't happen 
                    # because agents raise SessionPaused exception, but handle it just in case
                    # Extract iteration from result if available, default to 0
                    iteration = getattr(result, 'current_iteration', 0)
                    await self._update_stage_execution_paused(child_execution_id, iteration, result)
                else:
                    # FAILED or other status
                    await self._update_stage_execution_failed(
                        child_execution_id,
                        result.error_message or "Execution failed"
                    )
                
                # Create metadata
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=config["llm_provider"] or self.settings.llm_provider,
                    iteration_strategy=config["iteration_strategy"] or agent.iteration_strategy.value,
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=result.status,
                    error_message=result.error_message,
                    token_usage=None
                )
                
                return (result, metadata)
                
            except SessionPaused as e:
                # Special handling for pause signal (not an error!)
                logger.info(f"{parallel_type} '{agent_name}' paused at iteration {e.iteration}")
                
                # Create paused result with conversation state for resume
                paused_result = AgentExecutionResult(
                    status=StageStatus.PAUSED,
                    agent_name=agent_name,
                    stage_name=stage.name,
                    timestamp_us=now_us(),
                    result_summary=f"Paused at iteration {e.iteration}",
                    paused_conversation_state=e.conversation.model_dump() if e.conversation else None,
                    error_message=None
                )
                
                # Update child stage as PAUSED (not failed!)
                await self._update_stage_execution_paused(child_execution_id, e.iteration, paused_result)
                
                # Create metadata with PAUSED status
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=config["llm_provider"] or self.settings.llm_provider,
                    iteration_strategy=config["iteration_strategy"] or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=StageStatus.PAUSED,
                    error_message=None,
                    token_usage=None
                )
                
                return (paused_result, metadata)
                
            except Exception as e:
                # All other exceptions are failures
                logger.error(f"{parallel_type} '{agent_name}' failed: {e}", exc_info=True)
                
                agent_completed_at_us = now_us()
                
                # Update child stage execution with failure
                await self._update_stage_execution_failed(child_execution_id, str(e))
                
                # Create failed result
                error_result = AgentExecutionResult(
                    status=StageStatus.FAILED,
                    agent_name=agent_name,
                    stage_name=stage.name,
                    timestamp_us=agent_completed_at_us,
                    result_summary=f"Execution failed: {str(e)}",
                    error_message=str(e)
                )
                
                # Create metadata for failed execution
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=config["llm_provider"] or self.settings.llm_provider,
                    iteration_strategy=config["iteration_strategy"] or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=StageStatus.FAILED,
                    error_message=str(e),
                    token_usage=None
                )
                
                return (error_result, metadata)
        
        # Execute all concurrently
        tasks = [execute_single(config, idx) for idx, config in enumerate(execution_configs)]
        results_and_metadata = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate results and metadata, handling exceptions
        results = []
        metadatas = []
        
        for idx, item in enumerate(results_and_metadata):
            if isinstance(item, Exception):
                logger.error(f"Unexpected exception in {parallel_type} {idx+1}: {item}")
                agent_name = execution_configs[idx]["agent_name"]
                
                error_result = AgentExecutionResult(
                    status=StageStatus.FAILED,
                    agent_name=agent_name,
                    stage_name=stage.name,
                    timestamp_us=now_us(),
                    result_summary=f"Unexpected error: {str(item)}",
                    error_message=str(item)
                )
                error_metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_configs[idx]["llm_provider"] or self.settings.llm_provider,
                    iteration_strategy=execution_configs[idx]["iteration_strategy"] or "unknown",
                    started_at_us=stage_started_at_us,
                    completed_at_us=now_us(),
                    status=StageStatus.FAILED,
                    error_message=str(item),
                    token_usage=None
                )
                results.append(error_result)
                metadatas.append(error_metadata)
            else:
                result, metadata = item
                results.append(result)
                metadatas.append(metadata)
        
        # Create stage metadata
        stage_completed_at_us = now_us()
        stage_metadata = ParallelStageMetadata(
            parent_stage_execution_id=parent_stage_execution_id,
            parallel_type=parallel_type,
            failure_policy=stage.failure_policy,
            started_at_us=stage_started_at_us,
            completed_at_us=stage_completed_at_us,
            agent_metadatas=metadatas
        )
        
        # Determine overall stage status based on failure policy
        # Count by all statuses
        completed_count = sum(1 for m in metadatas if m.status == StageStatus.COMPLETED)
        failed_count = sum(1 for m in metadatas if m.status == StageStatus.FAILED)
        paused_count = sum(1 for m in metadatas if m.status == StageStatus.PAUSED)
        
        # PAUSED takes priority over everything - if any agent paused, whole stage is paused
        if paused_count > 0:
            # Any agent paused = whole stage is paused (user can resume)
            overall_status = StageStatus.PAUSED
            logger.info(
                f"{parallel_type.capitalize()} stage '{stage.name}': "
                f"{completed_count} completed, {failed_count} failed, {paused_count} paused "
                f"-> Overall status: PAUSED"
            )
        elif stage.failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
            logger.info(
                f"{parallel_type.capitalize()} stage '{stage.name}' completed: {completed_count}/{len(metadatas)} succeeded, "
                f"policy={stage.failure_policy}, status={overall_status.value}"
            )
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
            logger.info(
                f"{parallel_type.capitalize()} stage '{stage.name}' completed: {completed_count}/{len(metadatas)} succeeded, "
                f"policy={stage.failure_policy}, status={overall_status.value}"
            )
        
        # Create parallel stage result
        parallel_result = ParallelStageResult(
            results=results,
            metadata=stage_metadata,
            status=overall_status,
            timestamp_us=stage_metadata.completed_at_us
        )
        
        # Update parent stage execution with result
        if overall_status == StageStatus.COMPLETED:
            await self._update_stage_execution_completed(parent_stage_execution_id, parallel_result)
        elif overall_status == StageStatus.PAUSED:
            # Handle paused parallel stage
            # Use a representative iteration count (timestamp as proxy since we don't track iteration in metadata)
            # Note: Individual child iterations are stored in their own stage_execution records
            representative_iteration = max(
                m.completed_at_us for m in metadatas if m.status == StageStatus.PAUSED
            ) // 1000  # Use timestamp as proxy since iteration not in metadata
            
            # Save parallel_result in parent stage (contains ALL agent results including paused ones)
            await self._update_stage_execution_paused(
                parent_stage_execution_id, 
                representative_iteration,
                parallel_result  # This preserves all agent results for resume
            )
            
            logger.info(
                f"Parallel stage '{stage.name}' paused: "
                f"{paused_count} agents paused, {completed_count} completed, {failed_count} failed"
            )
        else:  # FAILED
            error_msg = f"{parallel_type.capitalize()} stage failed: {failed_count}/{len(metadatas)} executions failed (policy: {stage.failure_policy})"
            await self._update_stage_execution_failed(parent_stage_execution_id, error_msg)
        
        return parallel_result
    
    async def _resume_parallel_stage(
        self,
        paused_parent_stage: 'StageExecution',
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: ChainConfigModel,
        stage_index: int
    ) -> ParallelStageResult:
        """
        Resume a paused parallel stage by re-executing only paused children.
        
        Completed and failed children are preserved from the original execution.
        Only agents in PAUSED status are re-executed.
        
        Args:
            paused_parent_stage: Parent stage execution that was paused
            chain_context: Chain context for session
            session_mcp_client: Session-scoped MCP client
            chain_definition: Full chain definition
            stage_index: Index of this stage in chain
            
        Returns:
            ParallelStageResult with merged results (completed + resumed)
        """
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            ParallelStageMetadata,
            ParallelStageResult,
        )
        
        logger.info(f"Resuming parallel stage '{paused_parent_stage.stage_name}'")
        
        # 1. Load all child stage executions
        children = await self.history_service.get_parallel_stage_children(
            paused_parent_stage.execution_id
        )
        
        # 2. Separate children by status
        completed_children = [c for c in children if c.status == StageStatus.COMPLETED.value]
        paused_children = [c for c in children if c.status == StageStatus.PAUSED.value]
        failed_children = [c for c in children if c.status == StageStatus.FAILED.value]
        
        logger.info(
            f"Parallel stage resume: {len(completed_children)} completed, "
            f"{len(paused_children)} paused, {len(failed_children)} failed"
        )
        
        if not paused_children:
            raise ValueError(
                f"No paused children found for parallel stage {paused_parent_stage.stage_name}"
            )
        
        # 3. Load original stage configuration from chain definition
        stage_config = chain_definition.stages[stage_index]
        
        # 4. Reconstruct completed results from database
        completed_results = []
        completed_metadatas = []
        
        for child in completed_children:
            if child.stage_output:
                result = AgentExecutionResult.model_validate(child.stage_output)
                completed_results.append(result)
                
                # Reconstruct metadata for completed child
                metadata = AgentExecutionMetadata(
                    agent_name=child.agent,
                    llm_provider="unknown",  # Not stored, will be recalculated
                    iteration_strategy="unknown",  # Not stored
                    started_at_us=child.started_at_us or 0,
                    completed_at_us=child.completed_at_us or 0,
                    status=StageStatus.COMPLETED,
                    error_message=None,
                    token_usage=None
                )
                completed_metadatas.append(metadata)
        
        # 5. Reconstruct failed results from database (preserve failures)
        failed_results = []
        failed_metadatas = []
        
        for child in failed_children:
            # Create failed result
            failed_result = AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name=child.agent,
                stage_name=child.stage_name,
                timestamp_us=child.completed_at_us or now_us(),
                result_summary=f"Failed: {child.error_message or 'Unknown error'}",
                error_message=child.error_message
            )
            failed_results.append(failed_result)
            
            # Reconstruct metadata
            metadata = AgentExecutionMetadata(
                agent_name=child.agent,
                llm_provider="unknown",
                iteration_strategy="unknown",
                started_at_us=child.started_at_us or 0,
                completed_at_us=child.completed_at_us or now_us(),
                status=StageStatus.FAILED,
                error_message=child.error_message,
                token_usage=None
            )
            failed_metadatas.append(metadata)
        
        # 6. Build execution configs for ONLY paused children
        execution_configs = []
        
        for child in paused_children:
            # Determine agent configuration
            # For multi-agent: look up in stage.agents list
            # For replica: reconstruct from naming pattern
            
            if paused_parent_stage.parallel_type == ParallelType.MULTI_AGENT.value:
                # Find matching agent config in stage definition
                agent_config = next(
                    (a for a in stage_config.agents if a.name == child.agent),
                    None
                )
                if not agent_config:
                    raise ValueError(f"Agent config not found for {child.agent}")
                
                config = {
                    "agent_name": child.agent,
                    "llm_provider": agent_config.llm_provider,
                    "iteration_strategy": agent_config.iteration_strategy,
                }
            else:  # REPLICA
                # Extract base agent name (e.g., "KubernetesAgent-1" -> "KubernetesAgent")
                base_agent = stage_config.agent
                
                config = {
                    "agent_name": child.agent,  # Keep replica name
                    "base_agent_name": base_agent,
                    "llm_provider": stage_config.llm_provider,
                    "iteration_strategy": stage_config.iteration_strategy,
                }
            
            execution_configs.append(config)
            
            # 7. Restore paused conversation state to chain_context
            if child.stage_output:
                paused_result = AgentExecutionResult.model_validate(child.stage_output)
                # Add to context so agent can resume from paused state
                chain_context.add_stage_result(child.stage_name, paused_result)
                logger.info(f"Restored paused state for {child.agent}")
        
        # 8. Execute ONLY paused children using existing parallel execution logic
        logger.info(f"Re-executing {len(paused_children)} paused agents")
        
        # Create temporary stage-like object for execution
        from types import SimpleNamespace
        resumed_stage = SimpleNamespace(
            name=stage_config.name,
            agent=stage_config.agent,
            failure_policy=stage_config.failure_policy,
            llm_provider=stage_config.llm_provider,
            iteration_strategy=stage_config.iteration_strategy
        )
        
        # Execute paused agents (this handles creating new child stage executions)
        resumed_result = await self._execute_parallel_stage(
            stage=resumed_stage,
            chain_context=chain_context,
            session_mcp_client=session_mcp_client,
            chain_definition=chain_definition,
            stage_index=stage_index,
            execution_configs=execution_configs,
            parallel_type=paused_parent_stage.parallel_type
        )
        
        # 9. Merge all results: completed + failed + resumed
        all_results = completed_results + failed_results + resumed_result.results
        all_metadatas = completed_metadatas + failed_metadatas + resumed_result.metadata.agent_metadatas
        
        # 10. Create final merged metadata
        merged_metadata = ParallelStageMetadata(
            parent_stage_execution_id=paused_parent_stage.execution_id,
            parallel_type=paused_parent_stage.parallel_type,
            failure_policy=stage_config.failure_policy,
            started_at_us=paused_parent_stage.started_at_us or now_us(),
            completed_at_us=now_us(),
            agent_metadatas=all_metadatas
        )
        
        # 11. Determine final status using same logic as initial execution
        completed_count = sum(1 for m in all_metadatas if m.status == StageStatus.COMPLETED)
        failed_count = sum(1 for m in all_metadatas if m.status == StageStatus.FAILED)
        paused_count = sum(1 for m in all_metadatas if m.status == StageStatus.PAUSED)
        
        if paused_count > 0:
            # Still has paused agents (hit max_iterations again on resume)
            final_status = StageStatus.PAUSED
            logger.warning(f"Parallel stage paused again: {paused_count} agents still paused")
        elif stage_config.failure_policy == FailurePolicy.ALL:
            final_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            final_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        # 12. Create final merged result
        merged_result = ParallelStageResult(
            results=all_results,
            metadata=merged_metadata,
            status=final_status,
            timestamp_us=merged_metadata.completed_at_us
        )
        
        # 13. Update parent stage with final result
        if final_status == StageStatus.COMPLETED:
            await self._update_stage_execution_completed(
                paused_parent_stage.execution_id, 
                merged_result
            )
        elif final_status == StageStatus.PAUSED:
            # Paused again - update with new pause state
            await self._update_stage_execution_paused(
                paused_parent_stage.execution_id,
                0,  # Iteration not meaningful for parallel stage
                merged_result
            )
        else:  # FAILED
            error_msg = f"Parallel stage failed after resume: {failed_count} agents failed"
            await self._update_stage_execution_failed(
                paused_parent_stage.execution_id,
                error_msg
            )
        
        logger.info(
            f"Parallel stage resume complete: {completed_count} completed, "
            f"{failed_count} failed, {paused_count} paused -> {final_status.value}"
        )
        
        return merged_result
    
    def _is_final_stage_parallel(self, chain_definition: "ChainConfigModel") -> bool:
        """
        Check if the last stage in the chain is a parallel stage.
        
        Args:
            chain_definition: Chain definition to check
            
        Returns:
            True if the last stage is parallel, False otherwise
        """
        if not chain_definition.stages:
            return False
        
        last_stage = chain_definition.stages[-1]
        return last_stage.agents is not None or last_stage.replicas > 1
    
    async def _synthesize_parallel_results(
        self,
        parallel_result: "ParallelStageResult",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel"
    ) -> AgentExecutionResult:
        """
        Automatically invoke built-in SynthesisAgent to synthesize parallel results.
        
        Called when parallel stage is the final stage (no follow-up stage).
        Creates a synthetic stage execution for SynthesisAgent.
        Returns synthesized final analysis.
        
        Args:
            parallel_result: The parallel stage result to synthesize
            chain_context: Chain context for this session
            session_mcp_client: Session-scoped MCP client
            chain_definition: Full chain definition
            
        Returns:
            Synthesized AgentExecutionResult from SynthesisAgent
        """
        logger.info("Invoking automatic SynthesisAgent synthesis for final parallel stage")
        
        # Create synthetic stage for SynthesisAgent
        from tarsy.models.agent_config import ChainStageConfigModel
        
        synthesis_stage = ChainStageConfigModel(
            name="synthesis",
            agent="SynthesisAgent",
            llm_provider=chain_definition.llm_provider  # Use chain-level provider if set
        )
        
        # Create stage execution record for synthesis
        synthesis_stage_index = len(chain_definition.stages)  # After all defined stages
        synthesis_stage_execution_id = await self._create_stage_execution(
            chain_context.session_id,
            synthesis_stage,
            synthesis_stage_index
        )
        
        try:
            # Mark synthesis stage as started
            await self._update_stage_execution_started(synthesis_stage_execution_id)
            
            # Resolve effective LLM provider for SynthesisAgent
            effective_provider = chain_definition.llm_provider
            
            # Get SynthesisAgent from factory
            synthesis_agent = self.agent_factory.get_agent(
                agent_identifier="SynthesisAgent",
                mcp_client=session_mcp_client,
                iteration_strategy=None,  # Uses SynthesisAgent's default (react)
                llm_provider=effective_provider
            )
            
            # Set stage execution ID for interaction tagging
            synthesis_agent.set_current_stage_execution_id(synthesis_stage_execution_id)
            
            # Update chain context to reflect synthesis stage
            original_stage = chain_context.current_stage_name
            chain_context.current_stage_name = "synthesis"
            
            # Execute SynthesisAgent with parallel results already in context
            logger.info("Executing SynthesisAgent to synthesize parallel investigation results")
            synthesis_result = await synthesis_agent.process_alert(chain_context)
            
            # Restore original stage name (for proper context)
            chain_context.current_stage_name = original_stage
            
            # Update synthesis stage execution as completed
            await self._update_stage_execution_completed(synthesis_stage_execution_id, synthesis_result)
            
            logger.info("SynthesisAgent synthesis completed successfully")
            return synthesis_result
            
        except Exception as e:
            error_msg = f"SynthesisAgent synthesis failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Update synthesis stage as failed
            await self._update_stage_execution_failed(synthesis_stage_execution_id, error_msg)
            
            # Create error result
            error_result = AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name="SynthesisAgent",
                stage_name="synthesis",
                timestamp_us=now_us(),
                result_summary=f"Synthesis failed: {str(e)}",
                error_message=error_msg
            )
            
            return error_result

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
            
            # Clear caches to free memory
            self.clear_caches()
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
