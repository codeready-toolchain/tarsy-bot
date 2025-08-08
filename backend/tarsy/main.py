"""
Tarsy-bot - FastAPI Application
Main entry point for the tarsy backend service.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Any
import re

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from tarsy.config.settings import get_settings
from tarsy.controllers.history_controller import router as history_router
from tarsy.database.init_db import get_database_info, initialize_database
from tarsy.models.alert import Alert, AlertResponse
from tarsy.models.alert_processing import AlertProcessingData, AlertKey
from tarsy.models.constants import AlertSessionStatus
from tarsy.services.alert_service import AlertService
from tarsy.services.websocket_manager import WebSocketManager
from tarsy.utils.logger import get_module_logger, setup_logging
from tarsy.utils.timestamp import now_us

# Setup logger for this module
logger = get_module_logger(__name__)

# Track currently processing alert keys to prevent duplicates
processing_alert_keys: Dict[str, str] = {}  # alert_key -> alert_id mapping
alert_keys_lock = asyncio.Lock()  # Protect the processing_alert_keys dict

alert_service: AlertService = None
websocket_manager: WebSocketManager = None
alert_processing_semaphore: asyncio.Semaphore = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global alert_service, websocket_manager, alert_processing_semaphore
    
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
    websocket_manager = WebSocketManager()
    
    # Startup
    await alert_service.initialize()
    
    # Initialize dashboard broadcaster
    await websocket_manager.initialize_dashboard_broadcaster()
    
    # Register integrated hook system (history + dashboard broadcasting)
    from tarsy.hooks import register_integrated_hooks
    register_integrated_hooks(websocket_manager)
    
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
    await websocket_manager.shutdown_dashboard_broadcaster()
    
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


@app.get("/alert-types", response_model=List[str])
async def get_alert_types():
    """Get supported alert types for the development/testing web interface.
    
    This endpoint returns a list of alert types used only for dropdown selection
    in the development/testing web interface. In production, external clients
    (like Alert Manager) can submit any alert type. The system analyzes all
    alert types using the provided runbook and available agent-specific MCP tools.
    """
    return alert_service.agent_registry.get_supported_alert_types()


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
        
        # Create alert structure for processing using Pydantic model
        alert = AlertProcessingData(
            alert_type=alert_data.alert_type,
            alert_data=normalized_data
        )
        
        # Generate alert key for duplicate detection
        alert_key = AlertKey.from_alert_data(alert)
        alert_key_str = str(alert_key)
        
        # Check for duplicate alerts already in progress
        async with alert_keys_lock:
            if alert_key_str in processing_alert_keys:
                existing_alert_id = processing_alert_keys[alert_key_str]
                logger.info(f"Duplicate alert detected - same as {existing_alert_id} (key: {alert_key_str})")
                
                return AlertResponse(
                    alert_id=existing_alert_id,  # Return the existing alert ID
                    status="duplicate",
                    message=f"Identical alert is already being processed (ID: {existing_alert_id}). Monitor that alert's progress instead."
                )
            
            # Generate unique alert ID (only if not duplicate)
            alert_id = str(uuid.uuid4())
            
            # Register the alert ID as valid
            alert_service.register_alert_id(alert_id)
            
            # Register this alert key as being processed
            processing_alert_keys[alert_key_str] = alert_id
        
        # Start background processing with normalized data
        asyncio.create_task(process_alert_background(alert_id, alert))
        
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
    try:
        await websocket_manager.connect_dashboard(websocket, user_id)
        
        # Send initial connection confirmation
        from tarsy.models.websocket_models import ConnectionEstablished
        connection_msg = ConnectionEstablished(user_id=user_id)
        await websocket_manager.dashboard_manager.send_to_user(
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
                    await websocket_manager.handle_dashboard_message(user_id, message)
                except json.JSONDecodeError:
                    # Send error response for invalid JSON
                    from tarsy.models.websocket_models import ErrorMessage
                    error_msg = ErrorMessage(message="Invalid JSON message format")
                    await websocket_manager.dashboard_manager.send_to_user(
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
        websocket_manager.disconnect_dashboard(user_id)


async def process_alert_background(alert_id: str, alert: AlertProcessingData):
    """Background task to process an alert with comprehensive error handling and concurrency control."""
    async with alert_processing_semaphore:
        start_time = datetime.now()
        try:
            logger.info(f"Starting background processing for alert {alert_id}")
            
            # Validate alert structure before processing (using Pydantic model)
            if not alert:
                raise ValueError("Invalid alert structure: alert object is required")
            
            if not alert.alert_type:
                raise ValueError("Invalid alert structure: missing required field 'alert_type'")
            
            if not alert.alert_data or not isinstance(alert.alert_data, dict):
                raise ValueError("Invalid alert structure: missing or invalid 'alert_data' field")
            
            # Log alert processing start
            alert_type = alert.alert_type or "unknown"
            logger.info(f"Processing alert {alert_id} of type '{alert_type}' with {len(alert.alert_data)} data fields")
            
            # Process with timeout to prevent hanging
            try:
                # Set a reasonable timeout (e.g., 10 minutes for alert processing)
                result = await asyncio.wait_for(
                    alert_service.process_alert(alert, api_alert_id=alert_id),
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
            
        except json.JSONDecodeError as e:
            # JSON parsing errors in agent processing
            error_msg = f"JSON parsing error in agent processing: {str(e)}"
            logger.error(f"Alert {alert_id} JSON error: {error_msg}")
            
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
            
            # Try to provide more context about the error
            error_context = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "processing_duration_seconds": duration,
                "alert_type": alert.alert_type if alert else "unknown"
            }
        
        finally:
            # Clean up alert key tracking regardless of success or failure
            if alert:
                alert_key = AlertKey.from_alert_data(alert)
                alert_key_str = str(alert_key)
                
                async with alert_keys_lock:
                    if alert_key_str in processing_alert_keys:
                        del processing_alert_keys[alert_key_str]
                        logger.debug(f"Cleaned up alert key tracking for {alert_key_str}")

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "tarsy.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    ) 