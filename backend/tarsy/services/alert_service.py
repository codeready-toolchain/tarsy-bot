"""
Alert Service for multi-layer agent architecture.

This module provides the service that delegates alert processing to
specialized agents based on alert type. It implements the multi-layer
agent architecture for alert processing.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import uuid
from typing import Dict, Any, Optional

import httpx
from cachetools import TTLCache

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
        self.mcp_client = MCPClient(settings, self.mcp_server_registry)
        self.llm_manager = LLMManager(settings)
        
        # Track API alert_id to session_id mapping for dashboard websocket integration
        # Using TTL cache to prevent memory leaks - entries expire after 4 hours
        self.alert_session_mapping: TTLCache = TTLCache(maxsize=10000, ttl=4*3600)
        
        # Track all valid alert IDs that have been generated
        # Using TTL cache to prevent memory leaks - entries expire after 4 hours
        self.valid_alert_ids: TTLCache = TTLCache(maxsize=10000, ttl=4*3600)
        
        # Initialize agent factory with dependencies
        self.agent_factory = None  # Will be initialized in initialize()
        
        logger.info(f"AlertService initialized with agent delegation support "
                   f"({len(self.parsed_config.agents)} configured agents, "
                   f"{len(self.parsed_config.mcp_servers)} configured MCP servers)")
        
    def _load_agent_configuration(self):
        """
        Load agent configuration from the configured file path.
        
        Returns:
            CombinedConfigModel: Parsed configuration with agents and MCP servers
        """
        try:
            config_loader = ConfigurationLoader(self.settings.agent_config_path)
            parsed_config = config_loader.load_and_validate()

            logger.info(f"Successfully loaded agent configuration from {self.settings.agent_config_path}: "
                       f"{len(parsed_config.agents)} agents, {len(parsed_config.mcp_servers)} MCP servers")

            return parsed_config

        except ConfigurationError as e:
            logger.error(f"Configuration error loading {self.settings.agent_config_path}: {e}")
            logger.warning("Continuing with built-in agents only")
            # Return empty configuration to continue with built-in agents
            from tarsy.models.agent_config import CombinedConfigModel
            return CombinedConfigModel(agents={}, mcp_servers={})

        except Exception as e:
            logger.error(f"Unexpected error loading agent configuration: {e}")
            logger.warning("Continuing with built-in agents only")
            # Return empty configuration to continue with built-in agents
            from tarsy.models.agent_config import CombinedConfigModel
            return CombinedConfigModel(agents={}, mcp_servers={})

    async def initialize(self):
        """
        Initialize the service and all dependencies.
        """
        try:
            # Initialize MCP client
            await self.mcp_client.initialize()
            
            # Validate LLM availability
            if not self.llm_manager.is_available():
                available_providers = self.llm_manager.list_available_providers()
                status = self.llm_manager.get_availability_status()
                raise Exception(
                    f"No LLM providers are available. "
                    f"Configured providers: {available_providers}, Status: {status}"
                )
            
            # Initialize agent factory with dependencies
            self.agent_factory = AgentFactory(
                llm_client=self.llm_manager,
                mcp_client=self.mcp_client,
                mcp_registry=self.mcp_server_registry,
                agent_configs=self.parsed_config.agents
            )
            
            logger.info("AlertService initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AlertService: {str(e)}")
            raise
    
    async def process_alert(
        self, 
        chain_context: ChainContext, 
        alert_id: str
    ) -> str:
        """
        Process an alert by delegating to the appropriate specialized agent.
        
        Args:
            chain_context: Chain context with all processing data
            alert_id: API alert ID for session mapping
            
        Returns:
            Analysis result as a string
        """
        try:
            # Step 1: Validate prerequisites
            if not self.llm_manager.is_available():
                raise Exception("Cannot process alert: No LLM providers are available")
                
            if not self.agent_factory:
                raise Exception("Agent factory not initialized - call initialize() first")
            
            # Step 2: Get chain for alert type
            try:
                chain_definition = self.chain_registry.get_chain_for_alert_type(chain_context.alert_type)
            except ValueError as e:
                error_msg = str(e)
                logger.error(f"Chain selection failed: {error_msg}")
                
                # Update history session with error
                self._update_session_error(chain_context.session_id, error_msg)
                    
                return self._format_error_response(chain_context, error_msg)
            
            logger.info(f"Selected chain '{chain_definition.chain_id}' for alert type '{chain_context.alert_type}'")
            
            # Create history session with chain info
            session_created = self._create_chain_history_session(chain_context, chain_definition)
            
            # Store API alert_id to session_id mapping if session was created
            if session_created:
                self.store_alert_session_mapping(alert_id, chain_context.session_id)
            
            # Update history session with processing start
            self._update_session_status(chain_context.session_id, AlertSessionStatus.IN_PROGRESS.value)
            
            # Step 3: Extract runbook from alert data and download once per chain
            runbook = chain_context.get_runbook_url()
            if not runbook:
                error_msg = "No runbook specified in alert data"
                logger.error(error_msg)
                self._update_session_error(chain_context.session_id, error_msg)
                return self._format_error_response(chain_context, error_msg)
            
            runbook_content = await self.runbook_service.download_runbook(runbook)
            
            # Step 4: Set up chain context
            chain_context.set_chain_context(chain_definition.chain_id)
            chain_context.set_runbook_content(runbook_content)
            
            # Step 5: Execute chain stages sequentially  
            chain_result = await self._execute_chain_stages(
                chain_definition=chain_definition,
                chain_context=chain_context
            )
            
            # Step 6: Format and return results
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
                self._update_session_completed(chain_context.session_id, AlertSessionStatus.COMPLETED.value, final_analysis=final_result)
                
                return final_result
            else:
                # Handle chain processing error
                error_msg = chain_result.error or 'Chain processing failed'
                logger.error(f"Chain processing failed: {error_msg}")
                
                # Update history session with processing error
                self._update_session_error(chain_context.session_id, error_msg)
                
                return self._format_error_response(chain_context, error_msg)
                
        except Exception as e:
            error_msg = f"Alert processing failed: {str(e)}"
            logger.error(error_msg)
            
            # Update history session with processing error
            self._update_session_error(chain_context.session_id, error_msg)
            
            return self._format_error_response(chain_context, error_msg)

    async def _execute_chain_stages(
        self, 
        chain_definition: ChainConfigModel, 
        chain_context: ChainContext
    ) -> ChainExecutionResult:
        """
        Execute chain stages sequentially with accumulated data flow.
        
        Args:
            chain_definition: Chain definition with stages
            chain_context: Chain context with all processing data
            
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
            for i, stage in enumerate(chain_definition.stages):
                logger.info(f"Executing stage {i+1}/{len(chain_definition.stages)}: '{stage.name}' with agent '{stage.agent}'")
                
                # Create stage execution record
                stage_execution_id = await self._create_stage_execution(chain_context.session_id, stage, i)
                
                # Update session current stage
                await self._update_session_current_stage(chain_context.session_id, i, stage_execution_id)
                
                try:
                    # Mark stage as started
                    await self._update_stage_execution_started(stage_execution_id)
                    
                    # Get agent instance with stage-specific strategy (always creates unique instance)
                    agent = self.agent_factory.get_agent(
                        agent_identifier=stage.agent,
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
            
            # Determine overall chain status
            # Any stage failure should fail the entire session
            if failed_stages > 0:
                overall_status = ChainStatus.FAILED  # Any stage failed = session failed
            else:
                overall_status = ChainStatus.COMPLETED  # All stages succeeded
            
            logger.info(f"Chain execution completed: {successful_stages} successful, {failed_stages} failed")
            
            # Set completion timestamp just before returning successful result
            timestamp_us = now_us()
            
            return ChainExecutionResult(
                status=overall_status,
                final_analysis=final_analysis,
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
            f"**Alert Type:** {chain_context.alert_type}",
            f"**Processing Agent:** {agent_name}",
            f"**Environment:** {_format_alert_environment(chain_context.alert_data)}",
            f"**Severity:** {_format_alert_severity(chain_context.alert_data)}",
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
            f"**Alert Type:** {chain_context.alert_type}",
            f"**Processing Chain:** {chain_definition.chain_id}",
            f"**Stages:** {len(chain_definition.stages)}",
            f"**Environment:** {_format_alert_environment(chain_context.alert_data)}",
            f"**Severity:** {_format_alert_severity(chain_context.alert_data)}",
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
            f"**Alert Type:** {chain_context.alert_type}",
            f"**Environment:** {_format_alert_environment(chain_context.alert_data)}",
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
            
            # Generate unique alert ID for this processing session
            timestamp_us = now_us()
            unique_id = uuid.uuid4().hex[:12]  # Use 12 chars for uniqueness
            alert_id = f"{chain_context.alert_type}_{unique_id}_{timestamp_us}"
            
            # Store chain information in session using ChainContext and ChainDefinition
            created_successfully = self.history_service.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition,
                alert_id=alert_id
            )
            
            if created_successfully:
                logger.info(f"Created chain history session {chain_context.session_id} for alert {alert_id} with chain {chain_definition.chain_id}")
                return True
            else:
                logger.warning(f"Failed to create chain history session for alert {alert_id} with chain {chain_definition.chain_id}")
                return False
            
        except Exception as e:
            logger.warning(f"Failed to create chain history session: {str(e)}")
            return False
    
    def store_alert_session_mapping(self, alert_id: str, session_id: str):
        """Store mapping between API alert ID and session ID for dashboard websocket integration."""
        self.alert_session_mapping[alert_id] = session_id
        logger.debug(f"Stored alert-session mapping: {alert_id} -> {session_id}")
    
    def get_session_id_for_alert(self, alert_id: str) -> Optional[str]:
        """Get session ID for an API alert ID."""
        return self.alert_session_mapping.get(alert_id)
    
    def register_alert_id(self, alert_id: str):
        """Register a valid alert ID."""
        self.valid_alert_ids[alert_id] = True  # Use cache as a key-only store
        logger.debug(f"Registered alert ID: {alert_id}")
    
    def alert_exists(self, alert_id: str) -> bool:
        """Check if an alert ID exists (has been generated)."""
        return alert_id in self.valid_alert_ids
    
    def _update_session_status(self, session_id: Optional[str], status: str):
        """
        Update history session status.
        
        Args:
            session_id: Session ID to update
            status: New status
        """
        try:
            if not session_id or not self.history_service or not self.history_service.is_enabled:
                return
                
            self.history_service.update_session_status(
                session_id=session_id,
                status=status
            )
            
        except Exception as e:
            logger.warning(f"Failed to update session status: {str(e)}")
    
    def _update_session_completed(self, session_id: Optional[str], status: str, final_analysis: Optional[str] = None):
        """
        Mark history session as completed.
        
        Args:
            session_id: Session ID to complete
            status: Final status (e.g., 'completed', 'error')
            final_analysis: Final formatted analysis if status is completed successfully
        """
        try:
            if not session_id or not self.history_service or not self.history_service.is_enabled:
                return
                
            # The history service automatically sets completed_at_us when status is 'completed' or 'failed'
            self.history_service.update_session_status(
                session_id=session_id,
                status=status,
                final_analysis=final_analysis
            )
            
        except Exception as e:
            logger.warning(f"Failed to mark session completed: {str(e)}")
    
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
        Clear alert session mapping and valid alert ID caches.
        Useful for testing or manual cache cleanup.
        """
        self.alert_session_mapping.clear()
        self.valid_alert_ids.clear()
        logger.info("Cleared alert session mapping and valid alert ID caches")
    
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
            from tarsy.hooks.typed_context import stage_execution_context
            async with stage_execution_context(session_id, stage_execution) as ctx:
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
                from tarsy.hooks.typed_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
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
                from tarsy.hooks.typed_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
                    # Context automatically triggers hooks when exiting
                    pass
                logger.debug(f"Triggered stage hooks for stage failure {existing_stage.stage_index}: {existing_stage.stage_id}")
            except Exception as e:
                logger.warning(f"Failed to trigger stage failure hooks: {str(e)}")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as failed: {str(e)}")
    
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
                from tarsy.hooks.typed_context import stage_execution_context
                async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
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
            
            # Safely close MCP client (handle both sync and async close methods)
            if hasattr(self.mcp_client, 'close'):
                result = self.mcp_client.close()
                if asyncio.iscoroutine(result):
                    await result
            
            # Clear caches to free memory
            self.clear_caches()
            logger.info("AlertService resources cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
