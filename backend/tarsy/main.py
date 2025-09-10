"""
Tarsy-bot - FastAPI Application
Main entry point for the tarsy backend service.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional
import re
import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from cryptography.hazmat.primitives import serialization
from cachetools import TTLCache

from tarsy.config.settings import get_settings
from tarsy.controllers.history_controller import router as history_router
from tarsy.database.init_db import get_database_info, initialize_database
from tarsy.models.alert import Alert, AlertResponse
from tarsy.models.alert_processing import AlertKey
from tarsy.models.processing_context import ChainContext
from tarsy.services.alert_service import AlertService
from tarsy.services.dashboard_connection_manager import DashboardConnectionManager
from tarsy.utils.logger import get_module_logger, setup_logging
from tarsy.utils.timestamp import now_us

# Setup logger for this module
logger = get_module_logger(__name__)

# Track currently processing alert keys to prevent duplicates
processing_alert_keys: Dict[AlertKey, str] = {}  # alert_key -> alert_id mapping
alert_keys_lock = asyncio.Lock()  # Protect the processing_alert_keys dict

# JWT/JWKS caching to avoid loading/encoding public key on every request
jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)  # Cache for 1 hour

alert_service: Optional[AlertService] = None
dashboard_manager: Optional[DashboardConnectionManager] = None
alert_processing_semaphore: Optional[asyncio.Semaphore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
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
        logger.warning("History database initialization failed - continuing with history service disabled")
    
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
    
    alert_service = AlertService(settings)
    dashboard_manager = DashboardConnectionManager()
    
    # Startup
    await alert_service.initialize()
    
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
    title="Tarsy-bot",
    description="Automated incident response agent using AI and MCP servers",
    version="1.0.0",
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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Tarsy is running", "status": "healthy"}


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    try:
        # Get basic service status
        health_status = {
            "status": "healthy",
            "service": "tarsy",
            "timestamp": "2024-12-19T12:00:00Z",  # This will be updated by actual timestamp
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
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "service": "tarsy",
            "error": str(e)
        }

@app.get("/.well-known/jwks.json")
async def get_jwks():
    """Serve JSON Web Key Set (JWKS) for JWT token validation by oauth2-proxy.
    
    Uses caching to avoid loading and encoding the public key on every request.
    Cache TTL is 1 hour, which is reasonable for key rotation scenarios.
    """
    try:
        # Check cache first
        cache_key = "jwks"
        if cache_key in jwks_cache:
            logger.debug("JWKS served from cache")
            return jwks_cache[cache_key]
        
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
        
        return jwks
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JWKS endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "JWKS generation failed", 
                "message": "Unable to generate JSON Web Key Set"
            }
        )

@app.get("/alert-types", response_model=List[str])
async def get_alert_types():
    """Get supported alert types for the development/testing web interface.
    
    This endpoint returns a list of alert types used only for dropdown selection
    in the development/testing web interface. In production, external clients
    (like Alert Manager) can submit any alert type. The system analyzes all
    alert types using the provided runbook and available agent-specific MCP tools.
    """
    if alert_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return alert_service.chain_registry.list_available_alert_types()

@app.post("/alerts", response_model=AlertResponse)
async def submit_alert(request: Request):
    """Submit a new alert for processing with flexible data structure and comprehensive error handling."""
    try:
        # Check content length (prevent extremely large payloads)
        content_length = request.headers.get("content-length")
        MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10MB limit
        
        if content_length and int(content_length) > MAX_PAYLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "Payload too large",
                    "message": f"Request payload exceeds maximum size of {MAX_PAYLOAD_SIZE/1024/1024}MB",
                    "max_size_mb": MAX_PAYLOAD_SIZE/1024/1024
                }
            )
        
        # Parse JSON with error handling
        try:
            body = await request.body()
            if not body:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Empty request body",
                        "message": "Request body is required and cannot be empty",
                        "expected_fields": ["alert_type", "runbook", "data"]
                    }
                )
            
            raw_data = json.loads(body)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid JSON",
                    "message": f"Request body contains malformed JSON: {str(e)}",
                    "line": getattr(e, 'lineno', None),
                    "column": getattr(e, 'colno', None)
                }
            )
        
        # Validate and sanitize input data
        try:
            # Basic structure validation
            if not isinstance(raw_data, dict):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid data structure",
                        "message": "Request body must be a JSON object",
                        "received_type": type(raw_data).__name__
                    }
                )
            
            # Sanitize string fields to prevent XSS
            def sanitize_string(value: str) -> str:
                """Basic input sanitization to prevent XSS and injection attacks."""
                if not isinstance(value, str):
                    return value
                # Remove potentially dangerous characters
                sanitized = re.sub(r'[<>"\'\x00-\x1f\x7f-\x9f]', '', value)
                # Limit string length
                return sanitized[:10000]  # 10KB limit per string field
            
            # Deep sanitization of nested data
            def deep_sanitize(obj):
                """Recursively sanitize nested objects and arrays."""
                if isinstance(obj, dict):
                    return {k: deep_sanitize(v) for k, v in obj.items() if k}  # Remove empty keys
                elif isinstance(obj, list):
                    return [deep_sanitize(item) for item in obj[:1000]]  # Limit array size
                elif isinstance(obj, str):
                    return sanitize_string(obj)
                else:
                    return obj
            
            # Sanitize the entire payload
            sanitized_data = deep_sanitize(raw_data)
            
            # Validate using Alert model
            alert_data = Alert(**sanitized_data)
            
        except ValidationError as e:
            # Provide detailed validation error messages
            errors = []
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                errors.append({
                    "field": field_path,
                    "message": error["msg"],
                    "invalid_value": error.get("input"),
                    "expected_type": error["type"]
                })
            
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Validation failed",
                    "message": "One or more fields are invalid",
                    "validation_errors": errors,
                    "required_fields": ["alert_type", "runbook"],
                    "optional_fields": ["data", "severity", "timestamp"]
                }
            )
        
        # Additional business logic validation
        if not alert_data.alert_type or len(alert_data.alert_type.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid alert_type",
                    "message": "alert_type cannot be empty or contain only whitespace",
                    "field": "alert_type"
                }
            )
        
        if not alert_data.runbook or len(alert_data.runbook.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid runbook",
                    "message": "runbook cannot be empty or contain only whitespace",
                    "field": "runbook"
                }
            )
        
        # Check for suspicious patterns in runbook URL
        if alert_data.runbook and not re.match(r'^https?://', alert_data.runbook):
            logger.warning(f"Suspicious runbook URL format: {alert_data.runbook}")
        
        # Apply defaults for missing fields (inline normalization)
        normalized_data = alert_data.data.copy() if alert_data.data else {}
        
        # Apply defaults
        if alert_data.severity is None:
            normalized_data["severity"] = "warning"
        else:
            normalized_data["severity"] = alert_data.severity
            
        if alert_data.timestamp is None:
            normalized_data["timestamp"] = now_us()
        else:
            # Convert datetime to unix microseconds if needed
            if isinstance(alert_data.timestamp, datetime):
                normalized_data["timestamp"] = int(alert_data.timestamp.timestamp() * 1000000)
            else:
                normalized_data["timestamp"] = alert_data.timestamp
        
        # Apply default environment if not present in data
        if "environment" not in normalized_data:
            normalized_data["environment"] = "production"
        
        # Add required fields to data
        normalized_data["alert_type"] = alert_data.alert_type
        normalized_data["runbook"] = alert_data.runbook
        
        # Create alert structure for processing using ChainContext
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        
        # Create ChainContext for processing  
        alert_context = ChainContext(
            alert_type=alert_data.alert_type,
            alert_data=normalized_data,
            session_id=session_id,
            current_stage_name="initializing"  # Will be updated to actual stage names from config during execution
        )
        
        # Generate alert key for duplicate detection using normalized data
        alert_key = AlertKey.from_chain_context(alert_context)
        
        # Check for duplicate alerts already in progress
        async with alert_keys_lock:
            if alert_key in processing_alert_keys:
                existing_alert_id = processing_alert_keys[alert_key]
                logger.info(f"Duplicate alert detected - same as {existing_alert_id} (key: {alert_key})")
                
                return AlertResponse(
                    alert_id=existing_alert_id,  # Return the existing alert ID
                    status="duplicate",
                    message=f"Identical alert is already being processed (ID: {existing_alert_id}). Monitor that alert's progress instead."
                )
            
            # Generate unique alert ID (only if not duplicate)
            alert_id = str(uuid.uuid4())
            
            # Register the alert ID as valid
            if alert_service is None:
                raise HTTPException(status_code=503, detail="Service not initialized")
            alert_service.register_alert_id(alert_id)
            
            # Register this alert key as being processed
            processing_alert_keys[alert_key] = alert_id
        
        # Start background processing with normalized data
        asyncio.create_task(process_alert_background(alert_id, alert_context))
        
        logger.info(f"Alert {alert_id} submitted successfully with type: {alert_data.alert_type}")
        
        return AlertResponse(
            alert_id=alert_id,
            status="queued",
            message="Alert submitted for processing and validation completed"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (these are expected validation errors)
        raise
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error in submit_alert: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred while processing the alert",
                "support_info": "Please check the server logs or contact support if this persists"
            }
        )

@app.get("/session-id/{alert_id}")
async def get_session_id(alert_id: str):
    """Get session ID for an alert.
    Needed for dashboard websocket subscription because
    the client which sent the alert request needs to know the session ID (generated later)
    to subscribe to the alert updates."""
    if alert_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Check if the alert_id exists
    if not alert_service.alert_exists(alert_id):
        raise HTTPException(status_code=404, detail=f"Alert ID '{alert_id}' not found")
    
    session_id = alert_service.get_session_id_for_alert(alert_id)
    if session_id:
        return {"alert_id": alert_id, "session_id": session_id}
    else:
        # Session might not be created yet or history is disabled
        return {"alert_id": alert_id, "session_id": None}

@app.websocket("/ws/dashboard/{user_id}")
async def dashboard_websocket_endpoint(websocket: WebSocket, user_id: str):
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
        logger.error(f"Dashboard WebSocket error for user {user_id}: {str(e)}")
    finally:
        dashboard_manager.disconnect(user_id)

async def process_alert_background(alert_id: str, alert: ChainContext):
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
                # Set a reasonable timeout (e.g., 10 minutes for alert processing)
                await asyncio.wait_for(
                    alert_service.process_alert(alert, alert_id=alert_id),
                    timeout=600  # 10 minutes
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Alert processing exceeded timeout limit of 10 minutes")
            
            # Calculate processing duration
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Alert {alert_id} processed successfully in {duration:.2f} seconds")
            
        except ValueError as e:
            # Configuration or data validation errors
            error_msg = f"Invalid alert data: {str(e)}"
            logger.error(f"Alert {alert_id} validation failed: {error_msg}")
            
        except TimeoutError as e:
            # Processing timeout
            error_msg = str(e)
            logger.error(f"Alert {alert_id} processing timeout: {error_msg}")
            
        except ConnectionError as e:
            # Network or external service errors
            error_msg = f"Connection error during processing: {str(e)}"
            logger.error(f"Alert {alert_id} connection error: {error_msg}")
            
        except MemoryError as e:
            # Memory issues with large payloads
            error_msg = "Processing failed due to memory constraints (payload too large)"
            logger.error(f"Alert {alert_id} memory error: {error_msg}")
            
        except Exception as e:
            # Catch-all for unexpected errors
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Unexpected processing error: {str(e)}"
            logger.error(
                f"Alert {alert_id} unexpected error after {duration:.2f}s: {error_msg}", 
                exc_info=True
            )
        
        finally:
            # Clean up alert key tracking regardless of success or failure
            if alert:
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