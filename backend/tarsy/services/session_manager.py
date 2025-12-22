"""
Session Manager for session/history management.

This module handles all session management operations including:
- Creating history sessions for chain processing
- Updating session status and metadata
- Handling session errors
"""

from typing import Optional, TYPE_CHECKING

from tarsy.models.constants import AlertSessionStatus
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainConfigModel
    from tarsy.models.processing_context import ChainContext
    from tarsy.services.history_service import HistoryService

logger = get_module_logger(__name__)


class SessionManager:
    """
    Manages session lifecycle for alert processing chains.
    
    This class handles:
    - Creating history sessions with chain context
    - Updating session status and metadata
    - Handling session errors
    """
    
    def __init__(self, history_service: "HistoryService"):
        """
        Initialize the session manager.
        
        Args:
            history_service: History service for database operations
        """
        self.history_service = history_service
    
    def create_chain_history_session(
        self, 
        chain_context: "ChainContext", 
        chain_definition: "ChainConfigModel"
    ) -> bool:
        """
        Create a history session for chain processing.
        
        Args:
            chain_context: Chain context with all processing data
            chain_definition: Chain definition that will be executed
            
        Returns:
            True if created successfully, False if history service unavailable or creation failed
            
        Note:
            This method returns False for multiple failure scenarios (history service unavailable,
            creation failed, exception). Callers cannot distinguish between these cases without
            checking logs. This is acceptable for current usage patterns, but consider returning
            a tuple or result object if differentiated handling becomes necessary.
        """
        try:
            if not self.history_service:
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
    
    def update_session_status(
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
            final_analysis_summary: Optional final analysis summary if completed
            pause_metadata: Optional pause metadata if paused
            
        Raises:
            Exception: Re-raises any exception from history service to ensure visibility
                      of critical issues (DB failures, bugs, etc.)
        """
        # Graceful degradation: skip if no session or history service unavailable
        if not session_id or not self.history_service:
            return
            
        # Let exceptions propagate - they indicate serious issues that should be visible
        self.history_service.update_session_status(
            session_id=session_id,
            status=status,
            error_message=error_message,
            final_analysis=final_analysis,
            final_analysis_summary=final_analysis_summary,
            pause_metadata=pause_metadata
        )
    
    def update_session_error(self, session_id: Optional[str], error_message: str):
        """
        Mark history session as failed with error.
        
        Args:
            session_id: Session ID to update
            error_message: Error message
            
        Note:
            This method is typically called from exception handlers. To avoid masking
            the original error, exceptions from history service are logged but NOT re-raised.
            This ensures the original error is properly propagated to the caller.
        """
        # Graceful degradation: skip if no history service or no session
        if not session_id or not self.history_service:
            return
            
        try:
            # Status 'failed' will automatically set completed_at_us in the history service
            self.history_service.update_session_status(
                session_id=session_id,
                status=AlertSessionStatus.FAILED.value,
                error_message=error_message
            )
        except Exception as e:
            # Log but don't re-raise: this method is called from exception handlers,
            # and we don't want to mask the original error
            logger.error(f"Failed to update session error: {str(e)}", exc_info=True)

