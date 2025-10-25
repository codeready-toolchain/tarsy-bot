"""
TARSy - FastAPI Application
Main entry point for the tarsy backend service.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional, AsyncGenerator
import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cachetools import TTLCache

from tarsy.config.settings import get_settings
from tarsy.controllers.history_controller import router as history_router
from tarsy.controllers.alert_controller import router as alert_router
from tarsy.controllers.websocket_controller import websocket_router
from tarsy.database.init_db import (
    get_database_info,
    initialize_database,
    initialize_async_database,
    get_async_session_factory,
    dispose_async_database
)
from tarsy.models.processing_context import ChainContext
from tarsy.services.alert_service import AlertService
from tarsy.utils.logger import get_module_logger, setup_logging

if TYPE_CHECKING:
    from tarsy.services.events.manager import EventSystemManager
    from tarsy.services.history_cleanup_service import HistoryCleanupService
    from tarsy.services.mcp_health_monitor import MCPHealthMonitor
    from tarsy.repositories.base_repository import DatabaseManager

# Setup logger for this module
logger = get_module_logger(__name__)


def get_pod_id() -> str:
    """
    Get the current pod/instance identifier from environment
    
    Returns:
        Pod identifier from TARSY_POD_ID environment variable, or "unknown" if not set.
        In multi-replica deployments, this should be set to the pod name.
    """
    return os.environ.get("TARSY_POD_ID", "unknown")


# JWT/JWKS caching to avoid loading/encoding public key on every request
jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)  # Cache for 1 hour

alert_service: Optional[AlertService] = None
alert_processing_semaphore: Optional[asyncio.Semaphore] = None
event_system_manager: Optional["EventSystemManager"] = None
history_cleanup_service: Optional["HistoryCleanupService"] = None
mcp_health_monitor: Optional["MCPHealthMonitor"] = None  # MCPHealthMonitor for server health monitoring
db_manager: Optional["DatabaseManager"] = None  # DatabaseManager for history cleanup service

# Task tracking for session cancellation
active_tasks: Dict[str, asyncio.Task] = {}  # Maps session_id to asyncio Task
active_tasks_lock: Optional[asyncio.Lock] = None  # Initialized in lifespan()


async def handle_cancel_request(event: dict) -> None:
    """
    Handle cross-pod cancellation requests.
    
    This handler is called when a cancellation request is received on the
    'cancellations' channel. If this pod owns the session task, it will
    cancel it.
    
    Args:
        event: Event dict containing session_id
    """
    session_id = event.get("session_id")
    if not session_id:
        logger.warning("Received cancel request without session_id")
        return
    
    assert active_tasks_lock is not None, "active_tasks_lock not initialized"
    async with active_tasks_lock:
        task = active_tasks.get(session_id)
    
    if task:
        logger.info(f"Cancelling session {session_id} on this pod")
        task.cancel()
        # The task cleanup in process_alert_background will handle:
        # - Removing from active_tasks
        # - Updating status to CANCELLED
        # - Publishing session.cancelled event
    else:
        logger.debug(f"Session {session_id} not found on this pod (owned by another pod)")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    global alert_service, alert_processing_semaphore, event_system_manager, history_cleanup_service, mcp_health_monitor, db_manager, active_tasks_lock
    
    # Initialize services
    settings = get_settings()
    
    # Setup logging
    setup_logging(settings.log_level)
    
    # Initialize concurrency control
    alert_processing_semaphore = asyncio.Semaphore(settings.max_concurrent_alerts)
    active_tasks_lock = asyncio.Lock()
    logger.info(f"Alert processing concurrency limit: {settings.max_concurrent_alerts}")
    
    # Initialize database for history service
    db_init_success = initialize_database()
    if not db_init_success and settings.history_enabled:
        logger.critical(
            "History service is enabled but database initialization failed. "
            "This is a critical dependency - exiting to allow restart."
        )
        import sys
        sys.exit(1)  # Exit with error code
    
    # Clean up any orphaned sessions from previous pod crashes
    # Timeout-based detection: sessions with no interaction for configured timeout are marked as failed
    # This should happen after database initialization but before processing new alerts
    if settings.history_enabled and db_init_success:
        try:
            from tarsy.services.history_service import get_history_service
            history_service = get_history_service()
            cleaned_sessions = history_service.cleanup_orphaned_sessions(settings.orphaned_session_timeout_minutes)
            if cleaned_sessions > 0:
                logger.info(f"Startup cleanup: marked {cleaned_sessions} orphaned sessions as failed")
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned sessions during startup: {str(e)}")
    
    # Initialize AlertService - fail fast on critical configuration errors
    try:
        alert_service = AlertService(settings)
        
        # Startup
        await alert_service.initialize()
    except Exception as e:
        logger.critical(
            f"Failed to initialize AlertService: {str(e)}. "
            "This indicates a critical configuration error - exiting to allow restart."
        )
        import sys
        sys.exit(1)  # Exit with error code
    
    # Start MCP health monitoring (after AlertService is ready)
    # Uses dedicated health_check_mcp_client to avoid interfering with alert sessions
    try:
        from tarsy.services.mcp_health_monitor import MCPHealthMonitor
        from tarsy.services.system_warnings_service import get_warnings_service
        
        mcp_health_monitor = MCPHealthMonitor(
            mcp_client=alert_service.health_check_mcp_client,
            warnings_service=get_warnings_service(),
            check_interval=15.0  # Check every 15 seconds
        )
        await mcp_health_monitor.start()
        logger.info("MCP health monitoring started")
    except Exception as e:
        logger.error(f"Failed to start MCP health monitor: {e}", exc_info=True)
        logger.warning("Application will continue without MCP health monitoring")
    
    # Initialize typed hook system
    from tarsy.hooks.hook_registry import get_hook_registry
    from tarsy.services.history_service import get_history_service
    hook_registry = get_hook_registry()
    if settings.history_enabled and db_init_success:
        history_service = get_history_service()
        await hook_registry.initialize_hooks(history_service=history_service)
        logger.info("Typed hook system initialized successfully")
    else:
        logger.info("Typed hook system skipped - history service disabled")
    
    # Initialize event system (async database engine and event manager)
    try:
        from tarsy.services.events.manager import EventSystemManager, set_event_system
        
        # Initialize async database engine for event system
        initialize_async_database(settings.database_url)
        
        # Create and start event system manager
        event_system_manager = EventSystemManager(
            database_url=settings.database_url,
            db_session_factory=get_async_session_factory(),
            event_retention_hours=settings.event_retention_hours,
            event_cleanup_interval_hours=settings.event_cleanup_interval_hours
        )
        await event_system_manager.start()
        set_event_system(event_system_manager)
        logger.info("Event system started successfully")
        
        # Register cancellation handler for cross-pod cancellation
        from tarsy.services.events.channels import EventChannel
        await event_system_manager.register_channel_handler(
            EventChannel.CANCELLATIONS,
            handle_cancel_request
        )
        logger.info("Registered cancellation handler for cross-pod coordination")
    except Exception as e:
        logger.error(f"Failed to initialize event system: {e}", exc_info=True)
        logger.warning("Application will continue without event system")
    
    # Initialize history cleanup service
    if settings.history_enabled and db_init_success:
        try:
            from tarsy.services.history_cleanup_service import HistoryCleanupService
            from tarsy.repositories.base_repository import DatabaseManager
            
            # Create and initialize database manager for sync operations
            # Stored at module level to allow cleanup during shutdown
            db_manager = DatabaseManager(settings.database_url)
            db_manager.initialize()
            
            # Create and start history cleanup service
            # Handles both orphaned sessions (every 10m) and old history retention (every 12h)
            history_cleanup_service = HistoryCleanupService(
                db_session_factory=db_manager.get_session,
                retention_days=settings.history_retention_days,
                retention_cleanup_interval_hours=settings.history_cleanup_interval_hours,
                orphaned_timeout_minutes=settings.orphaned_session_timeout_minutes,
                orphaned_check_interval_minutes=settings.orphaned_session_check_interval_minutes,
            )
            await history_cleanup_service.start()
            logger.info("History cleanup service started successfully (handles orphaned sessions + retention)")
        except Exception as e:
            logger.critical(
                f"Failed to initialize history cleanup service: {e}. "
                "This is a critical dependency - exiting to allow restart."
            )
            import sys
            sys.exit(1)
    
    # Set up app state with callback to avoid circular imports
    # The controller will access this callback instead of importing process_alert_background directly
    app.state.process_alert_callback = process_alert_background
    
    logger.info("Tarsy started successfully!")
    
    # Log history service status
    db_info = get_database_info()
    if db_info.get("enabled"):
        logger.info(f"History service: ENABLED (Database: {db_info.get('database_name', 'unknown')})")
    else:
        logger.info("History service: DISABLED")
    
    yield
    
    # Shutdown: Mark in-progress sessions as interrupted for graceful shutdown
    logger.info("Tarsy shutting down...")
    
    # Stop MCP health monitor
    if mcp_health_monitor is not None:
        try:
            await mcp_health_monitor.stop()
            logger.info("MCP health monitor stopped")
        except Exception as e:
            logger.error(f"Error stopping MCP health monitor: {e}", exc_info=True)
    
    if settings.history_enabled and db_init_success:
        try:
            from tarsy.services.history_service import get_history_service
            history_service = get_history_service()
            pod_id = get_pod_id()
            interrupted_count = await history_service.mark_pod_sessions_interrupted(pod_id)
            if interrupted_count > 0:
                logger.info(f"Graceful shutdown: marked {interrupted_count} sessions as interrupted for pod {pod_id}")
        except Exception as e:
            logger.error(f"Failed to mark sessions as interrupted during shutdown: {str(e)}")
    
    # Shutdown history cleanup service
    if history_cleanup_service is not None:
        try:
            await history_cleanup_service.stop()
            logger.info("History cleanup service stopped")
        except Exception as e:
            logger.error(f"Error stopping history cleanup service: {e}", exc_info=True)
    
    # Cleanup database manager for history cleanup service
    if db_manager is not None:
        try:
            db_manager.close()
            logger.info("History cleanup database manager closed")
        except Exception as e:
            logger.error(f"Error closing database manager: {e}", exc_info=True)
    
    # Shutdown event system
    if event_system_manager is not None:
        try:
            await event_system_manager.stop()
            await dispose_async_database()
            logger.info("Event system stopped")
        except Exception as e:
            logger.error(f"Error stopping event system: {e}", exc_info=True)
    
    if alert_service is not None:
        await alert_service.close()
    logger.info("Tarsy shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="TARSy",
    description="Automated incident response agent using AI and MCP servers",
    version="0.0.1",
    lifespan=lifespan
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(history_router, tags=["history"])
app.include_router(alert_router, tags=["alerts"])
app.include_router(websocket_router, tags=["websocket"])

from tarsy.controllers.system_controller import router as system_router
app.include_router(system_router, prefix="/api/v1", tags=["system"])


@app.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint for Kubernetes probes
    
    Returns:
        - HTTP 200: All critical systems healthy
        - HTTP 503: Critical system degraded/unhealthy (Kubernetes will restart pod)
    """
    try:
        from tarsy.utils.version import VERSION
        
        # Get basic service status
        health_status = {
            "status": "healthy",
            "service": "tarsy",
            "version": VERSION,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        
        # Check history service / database
        db_info = get_database_info()
        history_status = "disabled"
        if db_info.get("enabled"):
            if db_info.get("connection_test"):
                history_status = "healthy"
            else:
                history_status = "unhealthy"
                health_status["status"] = "degraded"
        
        # Check event system
        event_system_status = "unknown"
        event_listener_type = "unknown"
        try:
            from tarsy.services.events.manager import get_event_system
            from tarsy.services.events.postgresql_listener import PostgreSQLEventListener
            
            event_system = get_event_system()
            event_listener = event_system.get_listener() if event_system else None
            
            if event_listener is None:
                event_system_status = "not_initialized"
                event_listener_type = "none"
            elif isinstance(event_listener, PostgreSQLEventListener):
                # Check both running flag AND PostgreSQL connection
                listener_conn = event_listener.listener_conn
                conn_healthy = (
                    listener_conn is not None and
                    not listener_conn.is_closed()  # asyncpg connection check
                )
                if event_listener.running and conn_healthy:
                    event_system_status = "healthy"
                else:
                    event_system_status = "degraded"
                    health_status["status"] = "degraded"
                event_listener_type = "PostgreSQLEventListener"
            else:
                # SQLite or other listener - just check running flag
                if event_listener.running:
                    event_system_status = "healthy"
                else:
                    event_system_status = "degraded"
                    health_status["status"] = "degraded"
                event_listener_type = event_listener.__class__.__name__
                
        except RuntimeError:
            event_system_status = "not_initialized"
            health_status["status"] = "degraded"
        except Exception as e:
            logger.debug(f"Error getting event system status: {e}")
            event_system_status = "error"
        
        # Build services status
        health_status["services"] = {
            "alert_processing": "healthy",
            "history_service": history_status,
            "event_system": {
                "status": event_system_status,
                "type": event_listener_type
            },
            "database": {
                "enabled": db_info.get("enabled", False),
                "connected": db_info.get("connection_test", False) if db_info.get("enabled") else None,
                "retention_days": db_info.get("retention_days") if db_info.get("enabled") else None,
                "migration_version": db_info.get("migration_version") if db_info.get("enabled") else None
            }
        }
        
        # Check system warnings (non-critical issues like MCP initialization failures)
        from tarsy.services.system_warnings_service import get_warnings_service
        warnings_service = get_warnings_service()
        warnings = warnings_service.get_warnings()
        
        if warnings:
            health_status["warnings"] = [
                {
                    "category": w.category,
                    "message": w.message,
                    "timestamp": w.timestamp
                }
                for w in warnings
            ]
            health_status["warning_count"] = len(warnings)
            # Note: Warnings (like MCP failures) don't mark service as degraded
            # The service can still function without all MCP servers
        else:
            health_status["warnings"] = []
            health_status["warning_count"] = 0
        
        # Return HTTP 503 only for critical system failures (database, event system)
        # NOT for warnings like MCP initialization failures
        # This allows the pod to be marked ready even if some MCP servers fail
        if health_status["status"] in ("degraded", "unhealthy"):
            response.status_code = 503
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        # Critical failure - return 503
        response.status_code = 503
        return {
            "status": "unhealthy",
            "service": "tarsy",
            "error": str(e)
        }

@app.get("/.well-known/jwks.json")
async def get_jwks(response: Response) -> JSONResponse:
    """Serve JSON Web Key Set (JWKS) for JWT token validation by oauth2-proxy.
    
    Uses caching to avoid loading and encoding the public key on every request.
    Cache TTL is 1 hour, which is reasonable for key rotation scenarios.
    """
    try:
        # Check cache first
        cache_key = "jwks"
        if cache_key in jwks_cache:
            logger.debug("JWKS served from cache")
            # Add caching headers for cached responses
            response.headers["Cache-Control"] = "public, max-age=3600"
            return JSONResponse(content=jwks_cache[cache_key], status_code=200)
        
        # Get public key path from settings
        settings = get_settings()
        public_key_path = Path(settings.jwt_public_key_path)
        
        # Handle relative paths by resolving them from the backend directory
        if not public_key_path.is_absolute():
            # Relative paths are resolved from the backend directory (where the app runs)
            backend_dir = Path(__file__).parent.parent
            public_key_path = (backend_dir / public_key_path).resolve()
        
        if not public_key_path.exists():
            raise HTTPException(
                status_code=503, 
                detail={
                    "error": "JWT public key not available",
                    "message": "JWT authentication is not configured. Please run 'make generate-jwt-keys' to set up JWT authentication."
                }
            )
        
        # Load and process the public key
        with open(public_key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())
        
        # Validate that the loaded key is an RSA public key
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Invalid key type",
                    "message": "JWT public key must be an RSA public key"
                }
            )
        
        # Convert RSA public key to JWKS format
        public_numbers = public_key.public_numbers()
        
        def int_to_base64url(val: int) -> str:
            """Convert integer to base64url encoding for JWKS format."""
            val_bytes = val.to_bytes((val.bit_length() + 7) // 8, 'big')
            return base64.urlsafe_b64encode(val_bytes).decode('ascii').rstrip('=')
        
        # Create JWKS response
        jwks = {
            "keys": [
                {
                    "kty": "RSA",          # Key type
                    "use": "sig",          # Key usage: signature
                    "kid": "tarsy-api-key-1",  # Key ID
                    "alg": "RS256",        # Algorithm
                    "n": int_to_base64url(public_numbers.n),    # Modulus
                    "e": int_to_base64url(public_numbers.e)     # Exponent
                }
            ]
        }
        
        # Cache the result for future requests
        jwks_cache[cache_key] = jwks
        logger.debug("JWKS generated and cached successfully")
        
        # Add caching headers for fresh responses
        response.headers["Cache-Control"] = "public, max-age=3600"
        
        return JSONResponse(content=jwks, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"JWKS endpoint error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "JWKS generation failed", 
                "message": "Unable to generate JSON Web Key Set"
            }
        ) from e

def mark_session_as_failed(alert: Optional[ChainContext], error_msg: str) -> None:
    """
    Mark a session as failed if alert context is available.
    
    Args:
        alert: Alert context containing session_id
        error_msg: Error message describing the failure
    """
    if alert and hasattr(alert, 'session_id') and alert_service:
        alert_service._update_session_error(alert.session_id, error_msg)

async def process_alert_background(session_id: str, alert: ChainContext) -> None:
    """Background task to process an alert with comprehensive error handling and concurrency control."""
    if alert_processing_semaphore is None or alert_service is None:
        logger.error(f"Cannot process session {session_id}: services not initialized")
        return
        
    async with alert_processing_semaphore:
        start_time = datetime.now()
        settings = get_settings()
        
        try:
            logger.info(f"Starting background processing for session {session_id}")
            
            # Log alert processing start
            logger.info(f"Processing session {session_id} of type '{alert.processing_alert.alert_type}' with {len(alert.processing_alert.alert_data)} data fields")
            
            # Process with timeout to prevent hanging
            try:
                # Use configurable timeout for alert processing
                timeout_seconds = settings.alert_processing_timeout
                logger.info(f"Processing session {session_id} with {timeout_seconds}s timeout")
                
                # Create task explicitly so we can cancel it if needed
                task = asyncio.create_task(alert_service.process_alert(alert))
                
                # Register task for cancellation tracking
                assert active_tasks_lock is not None, "active_tasks_lock not initialized"
                async with active_tasks_lock:
                    active_tasks[session_id] = task
                
                try:
                    await asyncio.wait_for(task, timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    # Timeout occurred - try to cancel the task
                    logger.warning(f"Session {session_id} exceeded {timeout_seconds}s timeout, attempting to cancel task")
                    task.cancel()
                    try:
                        await task  # Wait for cancellation to complete
                    except asyncio.CancelledError:
                        logger.info(f"Session {session_id} task cancelled successfully")
                    except Exception as e:
                        logger.error(f"Error while cancelling session {session_id}: {e}")
                    raise TimeoutError(f"Alert processing exceeded timeout limit of {timeout_seconds}s") from None
            except asyncio.CancelledError:
                # Task was cancelled - check if this is user-requested cancellation
                logger.info(f"Session {session_id} task was cancelled")
                
                # Check if this is a user-requested cancellation (status is CANCELING)
                from tarsy.services.history_service import get_history_service
                from tarsy.services.events.event_helpers import publish_session_cancelled
                from tarsy.models.constants import AlertSessionStatus
                
                is_user_cancellation = False
                history_service = get_history_service()
                if history_service:
                    session = history_service.get_session(session_id)
                    is_user_cancellation = session and session.status == AlertSessionStatus.CANCELING.value
                    
                    if is_user_cancellation:
                        # User-requested cancellation
                        history_service.update_session_status(
                            session_id=session_id,
                            status=AlertSessionStatus.CANCELLED.value,
                            error_message="Session cancelled by user"
                        )
                        
                        # Publish cancellation event
                        await publish_session_cancelled(session_id)
                        logger.info(f"Session {session_id} cancelled by user request")
                    else:
                        # Other cancellation (spurious, not user-requested)
                        logger.warning(f"Session {session_id} cancelled (not user-requested)")
                
                raise  # Re-raise to preserve the original CancelledError
            
            # Calculate processing duration
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Session {session_id} processed successfully in {duration:.2f} seconds")
            
        except asyncio.CancelledError:
            # Handle cancellation explicitly to prevent it from being caught by Exception handler
            # Check if this is a user-requested cancellation
            from tarsy.services.history_service import get_history_service
            from tarsy.services.events.event_helpers import publish_session_cancelled
            from tarsy.models.constants import AlertSessionStatus
            
            is_user_cancellation = False
            history_service = get_history_service()
            if history_service:
                session = history_service.get_session(session_id)
                # Check for both CANCELING and CANCELLED status (inner handler may have already updated it)
                is_user_cancellation = session and session.status in (
                    AlertSessionStatus.CANCELING.value,
                    AlertSessionStatus.CANCELLED.value
                )
                
                if is_user_cancellation:
                    # User-requested cancellation - already handled in inner block
                    # Just exit without marking as failed
                    logger.info(f"Session {session_id} cancelled by user - exiting gracefully")
                    return
                else:
                    # Non-user cancellation (e.g., pod shutdown, other asyncio cancellation)
                    # Mark as failed with appropriate message
                    logger.warning(f"Session {session_id} cancelled (not user-requested) - marking as failed")
                    mark_session_as_failed(alert, "Session cancelled due to system shutdown or timeout")
            else:
                # History service not available, log and exit
                logger.warning(f"Session {session_id} cancelled but history service unavailable")
            
        except ValueError as e:
            # Configuration or data validation errors
            error_msg = f"Invalid alert data: {str(e)}"
            logger.error(f"Session {session_id} validation failed: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except TimeoutError as e:
            # Processing timeout
            error_msg = str(e)
            logger.error(f"Session {session_id} processing timeout: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except ConnectionError as e:
            # Network or external service errors
            error_msg = f"Connection error during processing: {str(e)}"
            logger.error(f"Session {session_id} connection error: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except MemoryError as e:
            # Memory issues with large payloads
            error_msg = f"Processing failed due to memory constraints: {str(e)}"
            logger.error(f"Session {session_id} memory error: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except Exception as e:
            # Catch-all for unexpected errors
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Unexpected processing error: {str(e)}"
            logger.exception(
                f"Session {session_id} unexpected error after {duration:.2f}s: {error_msg}"
            )
            mark_session_as_failed(alert, error_msg)
        
        finally:
            # Always remove task from active_tasks when done (success, failure, or cancellation)
            assert active_tasks_lock is not None, "active_tasks_lock not initialized"
            async with active_tasks_lock:
                active_tasks.pop(session_id, None)
            logger.debug(f"Removed session {session_id} from active tasks")

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "tarsy.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    ) 