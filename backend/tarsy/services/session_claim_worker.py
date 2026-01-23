"""
SessionClaimWorker - Global Alert Queue Management

Manages the global alert queue by periodically claiming PENDING sessions
from the database and dispatching them for processing when capacity is available.
"""

import asyncio
from typing import Callable, Optional

from tarsy.models.constants import AlertSessionStatus
from tarsy.services.history_service import HistoryService
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)


class SessionClaimWorker:
    """
    Background worker for claiming pending sessions from the global queue.
    
    Runs a periodic loop that:
    1. Checks if global capacity is available (active sessions < max_concurrent_alerts)
    2. Claims the next PENDING session atomically from the database
    3. Dispatches the claimed session to the processing callback
    4. Repeats until stopped
    
    Supports graceful shutdown and multiple concurrent instances (multi-pod).
    """
    
    def __init__(
        self,
        history_service: HistoryService,
        max_global_concurrent: int,
        claim_interval: float,
        process_callback: Callable,
        pod_id: str = "unknown"
    ):
        """
        Initialize SessionClaimWorker.
        
        Args:
            history_service: HistoryService for database operations
            max_global_concurrent: Maximum concurrent sessions across all pods
            claim_interval: Interval between claim attempts (seconds)
            process_callback: Callback function to process claimed sessions
                             Signature: async def process_callback(session_id: str, alert: ChainContext)
            pod_id: Pod identifier for this worker
        """
        self.history_service = history_service
        self.max_global_concurrent = max_global_concurrent
        self.claim_interval = claim_interval
        self.process_callback = process_callback
        self.pod_id = pod_id
        
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._running = False
    
    async def start(self) -> None:
        """Start the claim worker background task."""
        if self._running:
            logger.warning(f"SessionClaimWorker already running on pod {self.pod_id}")
            return
        
        self._running = True
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._claim_loop())
        logger.info(
            f"SessionClaimWorker started on pod {self.pod_id} "
            f"(global_limit={self.max_global_concurrent}, interval={self.claim_interval}s)"
        )
    
    async def stop(self) -> None:
        """Stop the claim worker gracefully."""
        if not self._running:
            return
        
        logger.info(f"Stopping SessionClaimWorker on pod {self.pod_id}")
        self._stop_event.set()
        
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"SessionClaimWorker on pod {self.pod_id} did not stop gracefully, cancelling")
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
        
        self._running = False
        logger.info(f"SessionClaimWorker stopped on pod {self.pod_id}")
    
    async def _claim_loop(self) -> None:
        """Main claim loop - runs until stopped."""
        try:
            while not self._stop_event.is_set():
                try:
                    # Check if we have capacity to process more sessions
                    if await self._has_capacity():
                        # Try to claim next pending session
                        claimed_session = await self._claim_next_session()
                        
                        if claimed_session:
                            # Dispatch claimed session for processing
                            await self._dispatch_session(claimed_session)
                        else:
                            # No pending sessions available - wait before retry
                            await asyncio.wait_for(
                                self._stop_event.wait(),
                                timeout=self.claim_interval
                            )
                    else:
                        # At capacity - wait before checking again
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self.claim_interval
                        )
                
                except asyncio.TimeoutError:
                    # Timeout from wait_for is expected - continue loop
                    continue
                except Exception as e:
                    logger.error(f"Error in claim loop on pod {self.pod_id}: {e}", exc_info=True)
                    # Wait before retry to avoid tight error loop
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self.claim_interval
                        )
                    except asyncio.TimeoutError:
                        continue
        
        except asyncio.CancelledError:
            logger.info(f"SessionClaimWorker claim loop cancelled on pod {self.pod_id}")
            raise
        except Exception as e:
            logger.error(f"Fatal error in claim loop on pod {self.pod_id}: {e}", exc_info=True)
            raise
    
    async def _has_capacity(self) -> bool:
        """
        Check if there is capacity to process more sessions.
        
        Returns:
            True if active sessions < max_global_concurrent, False otherwise
        """
        try:
            active_count = await self._count_active_sessions()
            has_capacity = active_count < self.max_global_concurrent
            
            if not has_capacity:
                logger.debug(
                    f"Pod {self.pod_id}: At capacity ({active_count}/{self.max_global_concurrent}), waiting..."
                )
            
            return has_capacity
        except Exception as e:
            logger.error(f"Failed to check capacity on pod {self.pod_id}: {e}")
            return False
    
    async def _count_active_sessions(self) -> int:
        """
        Count sessions currently in IN_PROGRESS state across all pods.
        
        Returns:
            Count of active sessions
        """
        try:
            # Run blocking database operation in executor
            count = await asyncio.to_thread(
                self.history_service.count_sessions_by_status,
                AlertSessionStatus.IN_PROGRESS.value
            )
            return count
        except Exception as e:
            logger.error(f"Failed to count active sessions: {e}")
            raise
    
    async def _claim_next_session(self) -> Optional[dict]:
        """
        Atomically claim the next PENDING session from the database.
        
        Returns:
            Dict with session_id and alert_context if claimed, None otherwise
        """
        try:
            # Run blocking database operation in executor
            session = await asyncio.to_thread(
                self.history_service.claim_next_pending_session,
                self.pod_id
            )
            
            if not session:
                return None
            
            logger.info(f"Pod {self.pod_id} claimed session {session.session_id} for processing")
            
            # Return session data needed for processing
            # alert_context will be reconstructed from session data
            return {
                "session_id": session.session_id,
                "alert_data": session.alert_data,
                "alert_type": session.alert_type,
                "author": session.author,
                "runbook_url": session.runbook_url,
                "mcp_selection": session.mcp_selection,
                "session_metadata": session.session_metadata,
                "started_at_us": session.started_at_us  # Timestamp for ProcessingAlert
            }
        
        except Exception as e:
            logger.error(f"Failed to claim next session on pod {self.pod_id}: {e}")
            return None
    
    async def _dispatch_session(self, session_data: dict) -> None:
        """
        Dispatch a claimed session to the processing callback.
        
        Args:
            session_data: Dict containing session_id and alert context data
        """
        try:
            session_id = session_data["session_id"]
            
            # Reconstruct ChainContext from session data
            from tarsy.models.processing_context import ChainContext
            from tarsy.models.alert import ProcessingAlert
            
            # Create ProcessingAlert from stored data
            processing_alert = ProcessingAlert(
                alert_type=session_data["alert_type"],
                alert_data=session_data["alert_data"],
                timestamp=session_data["started_at_us"],  # Required field - use session start time
                runbook_url=session_data.get("runbook_url"),
                mcp_selection=session_data.get("mcp_selection")
            )
            
            # Create ChainContext
            alert_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id=session_id,
                current_stage_name="resuming",  # Will be updated during execution
                author=session_data.get("author", "system")
            )
            
            # Copy session metadata if present
            if session_data.get("session_metadata"):
                alert_context.session_metadata = session_data["session_metadata"]
            
            # Dispatch to processing callback
            asyncio.create_task(self.process_callback(session_id, alert_context))
            logger.debug(f"Pod {self.pod_id} dispatched session {session_id} for processing")
            
        except Exception as e:
            logger.error(
                f"Failed to dispatch session {session_data.get('session_id', 'unknown')} "
                f"on pod {self.pod_id}: {e}",
                exc_info=True
            )
            
            # Mark session as failed if dispatch fails
            try:
                session_id = session_data.get("session_id")
                if session_id:
                    self.history_service.update_session_status(
                        session_id=session_id,
                        status=AlertSessionStatus.FAILED.value,
                        error_message=f"Failed to dispatch session: {str(e)}"
                    )
            except Exception as update_error:
                logger.error(f"Failed to mark session as failed: {update_error}")
