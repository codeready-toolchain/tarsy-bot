"""
Alert Controller

FastAPI controller for alert processing endpoints.
Provides REST API for submitting alerts and retrieving alert types.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from tarsy.models.alert import Alert, AlertResponse
from tarsy.models.alert_processing import AlertKey
from tarsy.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["alerts"])

# Track currently processing alert keys to prevent duplicates
processing_alert_keys: Dict[AlertKey, str] = {}  # alert_key -> alert_id mapping
alert_keys_lock = asyncio.Lock()  # Protect the processing_alert_keys dict


@router.get("/alert-types", response_model=List[str])
async def get_alert_types():
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


@router.get("/session-id/{alert_id}")
async def get_session_id(alert_id: str):
    """Get session ID for an alert.
    Needed for dashboard websocket subscription because
    the client which sent the alert request needs to know the session ID (generated later)
    to subscribe to the alert updates."""
    # Import here to avoid circular imports
    from tarsy.main import alert_service
    
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


@router.post("/alerts", response_model=AlertResponse)
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
            from tarsy.utils.timestamp import now_us
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
        from tarsy.models.processing_context import ChainContext
        from tarsy.main import process_alert_background, alert_service
        
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