"""
TARSy - FastAPI Application
Main entry point for the tarsy backend service.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional, AsyncGenerator
import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cachetools import TTLCache

from tarsy.config.settings import get_settings
from tarsy.controllers.history_controller import router as history_router
from tarsy.controllers.alert_controller import router as alert_router
from tarsy.database.init_db import get_database_info, initialize_database
from tarsy.models.alert_processing import AlertKey
from tarsy.models.processing_context import ChainContext
from tarsy.services.alert_service import AlertService
from tarsy.services.dashboard_connection_manager import DashboardConnectionManager
from tarsy.utils.logger import get_module_logger, setup_logging

# Setup logger for this module
logger = get_module_logger(__name__)


# JWT/JWKS caching to avoid loading/encoding public key on every request
jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)  # Cache for 1 hour

alert_service: Optional[AlertService] = None
dashboard_manager: Optional[DashboardConnectionManager] = None
alert_processing_semaphore: Optional[asyncio.Semaphore] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    global alert_service, dashboard_manager, alert_processing_semaphore
    
    # Initialize services
    settings = get_settings()
    
    # Setup logging
    setup_logging(settings.log_level)
    
    # Initialize concurrency control
    alert_processing_semaphore = asyncio.Semaphore(settings.max_concurrent_alerts)
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
    
    # Clean up any orphaned sessions from previous backend crashes
    # This should happen after database initialization but before processing new alerts
    if settings.history_enabled and db_init_success:
        try:
            from tarsy.services.history_service import get_history_service
            history_service = get_history_service()
            cleaned_sessions = history_service.cleanup_orphaned_sessions()
            if cleaned_sessions > 0:
                logger.info(f"Startup cleanup: marked {cleaned_sessions} orphaned sessions as failed")
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned sessions during startup: {str(e)}")
    
    # Initialize AlertService - fail fast on critical configuration errors
    try:
        alert_service = AlertService(settings)
        dashboard_manager = DashboardConnectionManager()
        
        # Startup
        await alert_service.initialize()
    except Exception as e:
        logger.critical(
            f"Failed to initialize AlertService: {str(e)}. "
            "This indicates a critical configuration error - exiting to allow restart."
        )
        import sys
        sys.exit(1)  # Exit with error code
    
    # Initialize dashboard broadcaster
    await dashboard_manager.initialize_broadcaster()
    
    # Initialize typed hook system
    from tarsy.hooks.hook_registry import get_typed_hook_registry
    from tarsy.services.history_service import get_history_service
    typed_hook_registry = get_typed_hook_registry()
    if settings.history_enabled and db_init_success:
        history_service = get_history_service()
        await typed_hook_registry.initialize_hooks(
            history_service=history_service,
            dashboard_broadcaster=dashboard_manager.broadcaster
        )
        logger.info("Typed hook system initialized successfully")
    else:
        logger.info("Typed hook system skipped - history service disabled")
    
    logger.info("Tarsy started successfully!")
    
    # Log history service status
    db_info = get_database_info()
    if db_info.get("enabled"):
        logger.info(f"History service: ENABLED (Database: {db_info.get('database_name', 'unknown')})")
    else:
        logger.info("History service: DISABLED")
    
    yield
    
    # Shutdown
    logger.info("Tarsy shutting down...")
    
    # Shutdown dashboard broadcaster
    if dashboard_manager is not None:
        await dashboard_manager.shutdown_broadcaster()
    
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

from tarsy.controllers.system_controller import router as system_router
app.include_router(system_router, prefix="/api/v1", tags=["system"])


@app.get("/")
async def root() -> Dict[str, str]:
    """Health check endpoint."""
    return {"message": "Tarsy is running", "status": "healthy"}


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check endpoint."""
    try:
        # Get basic service status
        health_status = {
            "status": "healthy",
            "service": "tarsy",
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        
        # Add history service status
        db_info = get_database_info()
        history_status = "disabled"
        if db_info.get("enabled"):
            if db_info.get("connection_test"):
                history_status = "healthy"
            else:
                history_status = "unhealthy"
                health_status["status"] = "degraded"  # Overall status degraded if history fails
        
        health_status["services"] = {
            "alert_processing": "healthy",
            "history_service": history_status,
            "database": {
                "enabled": db_info.get("enabled", False),
                "connected": db_info.get("connection_test", False) if db_info.get("enabled") else None,
                "retention_days": db_info.get("retention_days") if db_info.get("enabled") else None
            }
        }
        
        # Add system warnings
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
            
            # If there are warnings, mark status as degraded
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
        else:
            health_status["warnings"] = []
            health_status["warning_count"] = 0
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
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

@app.websocket("/ws/dashboard/{user_id}")
async def dashboard_websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    """WebSocket endpoint for dashboard real-time updates."""
    if dashboard_manager is None:
        await websocket.close(code=1011, reason="Service not initialized")
        return
        
    try:
        logger.info(f"🔌 New WebSocket connection from user: {user_id}")
        await dashboard_manager.connect(websocket, user_id)
        
        # Send initial connection confirmation
        from tarsy.models.websocket_models import ConnectionEstablished
        connection_msg = ConnectionEstablished(user_id=user_id)
        await dashboard_manager.send_to_user(
            user_id, 
            connection_msg.model_dump()
        )
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client (subscription requests, etc.)
                message_text = await websocket.receive_text()
                try:
                    message = json.loads(message_text)
                    await dashboard_manager.handle_subscription_message(user_id, message)
                except json.JSONDecodeError:
                    # Send error response for invalid JSON
                    from tarsy.models.websocket_models import ErrorMessage
                    error_msg = ErrorMessage(message="Invalid JSON message format")
                    await dashboard_manager.send_to_user(
                        user_id, 
                        error_msg.model_dump()
                    )
            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception(f"Dashboard WebSocket error for user {user_id}: {str(e)}")
    finally:
        dashboard_manager.disconnect(user_id)

def mark_session_as_failed(alert: Optional[ChainContext], error_msg: str) -> None:
    """
    Mark a session as failed if alert context is available.
    
    Args:
        alert: Alert context containing session_id
        error_msg: Error message describing the failure
    """
    if alert and hasattr(alert, 'session_id') and alert_service:
        alert_service._update_session_error(alert.session_id, error_msg)

async def process_alert_background(alert_id: str, alert: ChainContext) -> None:
    """Background task to process an alert with comprehensive error handling and concurrency control."""
    if alert_processing_semaphore is None or alert_service is None:
        logger.error(f"Cannot process alert {alert_id}: services not initialized")
        return
        
    async with alert_processing_semaphore:
        start_time = datetime.now()
        try:
            logger.info(f"Starting background processing for alert {alert_id}")
            
            # Log alert processing start
            logger.info(f"Processing alert {alert_id} of type '{alert.alert_type}' with {len(alert.alert_data)} data fields")
            
            # Process with timeout to prevent hanging
            try:
                # Use configurable timeout for alert processing
                timeout_seconds = settings.alert_processing_timeout
                await asyncio.wait_for(
                    alert_service.process_alert(alert, alert_id=alert_id),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Alert processing exceeded timeout limit of {timeout_seconds}s")
            
            # Calculate processing duration
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Alert {alert_id} processed successfully in {duration:.2f} seconds")
            
        except ValueError as e:
            # Configuration or data validation errors
            error_msg = f"Invalid alert data: {str(e)}"
            logger.error(f"Alert {alert_id} validation failed: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except TimeoutError as e:
            # Processing timeout
            error_msg = str(e)
            logger.error(f"Alert {alert_id} processing timeout: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except ConnectionError as e:
            # Network or external service errors
            error_msg = f"Connection error during processing: {str(e)}"
            logger.error(f"Alert {alert_id} connection error: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except MemoryError as e:
            # Memory issues with large payloads
            error_msg = "Processing failed due to memory constraints (payload too large)"
            logger.error(f"Alert {alert_id} memory error: {error_msg}")
            mark_session_as_failed(alert, error_msg)
            
        except Exception as e:
            # Catch-all for unexpected errors
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Unexpected processing error: {str(e)}"
            logger.exception(
                f"Alert {alert_id} unexpected error after {duration:.2f}s: {error_msg}"
            )
            mark_session_as_failed(alert, error_msg)
        
        finally:
            # Clean up alert key tracking regardless of success or failure
            if alert:
                from tarsy.controllers.alert_controller import processing_alert_keys, alert_keys_lock
                alert_key = AlertKey.from_chain_context(alert)
                
                async with alert_keys_lock:
                    if alert_key in processing_alert_keys:
                        del processing_alert_keys[alert_key]
                        logger.debug(f"Cleaned up alert key tracking for {alert_key}")

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "tarsy.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    ) 