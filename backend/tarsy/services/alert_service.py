"""
Alert Service for multi-layer agent architecture.

This module provides the service that delegates alert processing to
specialized agents based on alert type. It implements the multi-layer
agent architecture for alert processing.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Dict, Any, Optional
import asyncio

import httpx

from tarsy.models.processing_context import ChainContext
from tarsy.config.settings import Settings
from tarsy.config.agent_config import ConfigurationLoader, ConfigurationError
from tarsy.integrations.llm.client import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_config import ChainConfigModel

from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import AlertSessionStatus, StageStatus, ChainStatus
from tarsy.models.api_models import ChainExecutionResult
from tarsy.utils.timestamp import now_us
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.chain_registry import ChainRegistry
from tarsy.services.history_service import get_history_service
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.runbook_service import RunbookService
from tarsy.utils.logger import get_module_logger
from tarsy.agents.exceptions import SessionPaused
from tarsy.models.pause_metadata import PauseMetadata, PauseReason

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
                llm_client=self.llm_manager,
                mcp_registry=self.mcp_server_registry,
                agent_configs=self.parsed_config.agents,
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
                
                # Mark history session as completed successfully
                self._update_session_status(chain_context.session_id, AlertSessionStatus.COMPLETED.value, final_analysis=final_result)
                
                # Publish session.completed event
                from tarsy.services.events.event_helpers import publish_session_completed
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
            for stage_exec in stage_executions:
                if stage_exec.status == StageStatus.COMPLETED.value and stage_exec.stage_output:
                    # Reconstruct AgentExecutionResult from stage_output
                    result = AgentExecutionResult.model_validate(stage_exec.stage_output)
                    chain_context.add_stage_result(stage_exec.stage_name, result)
                elif stage_exec.status == StageStatus.PAUSED.value and stage_exec.stage_output:
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
            
            # Update stage status back to ACTIVE
            paused_stage.status = StageStatus.ACTIVE.value
            paused_stage.current_iteration = None  # Will be reset by agent
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(session_id, paused_stage):
                pass
            
            # Step 6: Create new MCP client and continue execution
            logger.info(f"Creating session-scoped MCP client for resumed session {session_id}")
            session_mcp_client = await self.mcp_client_factory.create_client()
            
            # Execute from the paused stage
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
                self._update_session_status(
                    session_id,
                    AlertSessionStatus.COMPLETED.value,
                    final_analysis=final_result,
                )
                from tarsy.services.events.event_helpers import publish_session_completed
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
                return error_msg
        
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
                
                # For resumed sessions, reuse existing stage execution ID for the paused stage
                # For new sessions or subsequent stages, create new stage execution record
                if i == start_from_stage and start_from_stage > 0:
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
                
                # Record stage transition as interaction (non-blocking)
                if self.history_service and hasattr(self.history_service, "record_session_interaction"):
                    rec = self.history_service.record_session_interaction
                    # If async, await directly; if sync, offload to thread
                    if asyncio.iscoroutinefunction(rec):
                        await rec(chain_context.session_id)
                    else:
                        await asyncio.to_thread(rec, chain_context.session_id)
                
                try:
                    # Mark stage as started
                    await self._update_stage_execution_started(stage_execution_id)
                    
                    # Get agent instance with stage-specific strategy (always creates unique instance)
                    # Pass session-scoped MCP client for isolation
                    agent = self.agent_factory.get_agent(
                        agent_identifier=stage.agent,
                        mcp_client=session_mcp_client,
                        iteration_strategy=stage.iteration_strategy
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
                        from tarsy.services.events.event_helpers import publish_session_paused
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
    async def _create_stage_execution(self, session_id: str, stage, stage_index: int) -> str:
        """
        Create a stage execution record.
        
        Args:
            session_id: Session ID
            stage: Stage definition
            stage_index: Stage index in chain
            
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
            status=StageStatus.PENDING.value
        )
        
        # Trigger stage execution hooks (history + dashboard) via context manager
        try:
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(session_id, stage_execution):
                # Context automatically triggers hooks when exiting
                # History hook will create DB record and set execution_id on the model
                pass
            logger.debug(f"Successfully created stage execution {stage_index}: {stage.name}")
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
            existing_stage.status = StageStatus.ACTIVE.value
            existing_stage.started_at_us = now_us()
            
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
