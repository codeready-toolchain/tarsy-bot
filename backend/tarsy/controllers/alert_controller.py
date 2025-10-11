"""
Alert Controller

FastAPI controller for alert processing endpoints.
Provides REST API for submitting alerts and retrieving alert types.
"""

import asyncio
import json
import re
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from tarsy.models.alert import Alert, AlertResponse, ProcessingAlert
from tarsy.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alert-types", response_model=list[str])
async def get_alert_types() -> list[str]:
    """Get supported alert types for the development/testing web interface.
    
    This endpoint returns a list of alert types used only for dropdown selection
    in the development/testing web interface. In production, external clients
    (like Alert Manager) can submit any alert type. The system analyzes all
    alert types using the provided runbook and available agent-specific MCP tools.
    """
    # Import here to avoid circular imports
    from tarsy.main import alert_service
    
    if alert_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return alert_service.chain_registry.list_available_alert_types()


@router.post("/alerts", response_model=AlertResponse)
async def submit_alert(request: Request) -> AlertResponse:
    """Submit a new alert for processing with flexible data structure and comprehensive error handling."""
    try:
        # Check content length (prevent extremely large payloads)
        MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10MB
        content_length_raw = request.headers.get("content-length")
        try:
            if content_length_raw is not None and int(content_length_raw) > MAX_PAYLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": "Payload too large",
                        "message": f"Request payload exceeds maximum size of {MAX_PAYLOAD_SIZE/1024/1024}MB",
                        "max_size_mb": MAX_PAYLOAD_SIZE/1024/1024,
                    },
                )
        except ValueError:
            # Ignore invalid Content-Length; we'll enforce after reading the body
            pass
        
        # Parse JSON with error handling
        try:
            body = await request.body()
            if len(body) > MAX_PAYLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": "Payload too large",
                        "message": f"Request payload exceeds maximum size of {MAX_PAYLOAD_SIZE/1024/1024}MB",
                        "max_size_mb": MAX_PAYLOAD_SIZE/1024/1024,
                    },
                )
            if not body:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Empty request body",
                        "message": "Request body is required and cannot be empty",
                        "required_fields": Alert.get_required_fields(),
                        "optional_fields": Alert.get_optional_fields()
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
                    "required_fields": Alert.get_required_fields(),
                    "optional_fields": Alert.get_optional_fields()
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
        
        # Validate runbook URL scheme for security (only if provided)
        if alert_data.runbook and len(alert_data.runbook.strip()) > 0:
            runbook_url = alert_data.runbook.strip()
            try:
                parsed_url = urlparse(runbook_url)
                scheme = parsed_url.scheme.lower()
                
                if not scheme or scheme not in ("http", "https"):
                    logger.error(f"Rejected unsafe runbook URL scheme '{scheme}': {runbook_url}")
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "Invalid runbook URL scheme",
                            "message": f"Runbook URL must use http or https protocol. Received scheme: '{scheme}'",
                            "field": "runbook",
                            "allowed_schemes": ["http", "https"],
                            "rejected_url": runbook_url
                        }
                    )
            except ValueError as e:
                logger.error(f"Invalid runbook URL format: {runbook_url} - {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid runbook URL format",
                        "message": f"Runbook URL is malformed: {str(e)}",
                        "field": "runbook"
                    }
                )
        
        # Transform API alert to ProcessingAlert (adds metadata, keeps data pristine)
        processing_alert = ProcessingAlert.from_api_alert(alert_data)
        
        # Generate session_id BEFORE starting background processing
        session_id = str(uuid.uuid4())
        
        # Create ChainContext for processing  
        from tarsy.models.processing_context import ChainContext
        
        # Create ChainContext from ProcessingAlert
        alert_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=session_id,
            current_stage_name="initializing"  # Will be updated to actual stage names from config during execution
        )
        
        # Start background processing using callback from app state
        # This avoids circular import by accessing the callback through FastAPI app state
        process_callback = request.app.state.process_alert_callback
        asyncio.create_task(process_callback(session_id, alert_context))
        
        logger.info(f"Alert submitted with session_id: {session_id}")
        
        # Return session_id immediately - client can use it right away
        return AlertResponse(
            session_id=session_id,
            status="queued",
            message="Alert submitted for processing"
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