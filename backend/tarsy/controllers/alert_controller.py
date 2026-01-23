"""
Alert Controller

FastAPI controller for alert processing endpoints.
Provides REST API for submitting alerts and retrieving alert types.
"""

import json
import re
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from tarsy.models.alert import Alert, AlertResponse, AlertTypesResponse, ProcessingAlert
from tarsy.utils.auth_helpers import extract_author_from_request
from tarsy.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alert-types", response_model=AlertTypesResponse)
async def get_alert_types() -> AlertTypesResponse:
    """Get supported alert types for the development/testing web interface.
    
    This endpoint returns alert types available to the clients and the default alert type
    which will be used if no alert type provided in the alert processing request.
    """
    # Import here to avoid circular imports
    from tarsy.main import alert_service
    
    if alert_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return AlertTypesResponse(
        alert_types=alert_service.chain_registry.list_available_alert_types(),
        default_alert_type=alert_service.chain_registry.get_default_alert_type()
    )


@router.get("/runbooks", response_model=list[str])
async def get_runbooks() -> list[str]:
    """Get list of runbook URLs from configured GitHub repository.
    
    Returns a list of markdown file URLs from the configured runbooks repository.
    If runbooks_repo_url is not configured or if fetching fails, returns an empty list.
    
    The dashboard will add "Default Runbook" option to this list, which when selected
    will not send a runbook field (allowing backend to use built-in defaults).
    
    Returns:
        List of GitHub URLs to runbook markdown files
    """
    from tarsy.config.settings import get_settings
    from tarsy.services.runbooks_service import RunbooksService
    
    try:
        settings = get_settings()
        runbooks_service = RunbooksService(settings)
        runbook_urls = await runbooks_service.get_runbooks()
        
        logger.info(f"Returning {len(runbook_urls)} runbook URLs")
        return runbook_urls
        
    except Exception as e:
        logger.error(f"Error fetching runbooks: {e}", exc_info=True)
        # Return empty list on error - don't fail the endpoint
        return []


@router.post("/alerts", response_model=AlertResponse)
async def submit_alert(request: Request) -> AlertResponse:
    """Submit a new alert for processing with flexible data structure and comprehensive error handling."""
    # Check if service is shutting down - reject new sessions immediately
    from tarsy.main import shutdown_in_progress
    
    if shutdown_in_progress:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service shutting down",
                "message": "Service is shutting down gracefully. Please retry your request.",
                "retry_after": 30  # Suggest retry after 30 seconds (another pod should be available)
            }
        )
    
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
                # Remove potentially dangerous characters while preserving newlines, tabs, and carriage returns
                # Keep: \t (0x09), \n (0x0A), \r (0x0D)
                # Remove: other control chars (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F, 0x7F-0x9F) and dangerous chars
                sanitized = re.sub(r'[<>"\'\x00-\x08\x0B\x0C\x0E-\x1f\x7f-\x9f]', '', value)
                # Limit string length to 1MB per field (sufficient for large log messages/stack traces)
                # Overall payload is still limited to 10MB at the request level
                return sanitized[:1000000]  # 1MB limit per string field
            
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
            
            # Apply data masking if enabled
            from tarsy.config.settings import get_settings
            settings = get_settings()
            
            if settings.alert_data_masking_enabled:
                try:
                    from tarsy.services.data_masking_service import DataMaskingService
                    
                    # Initialize masking service (no MCP registry needed for alert data masking)
                    masking_service = DataMaskingService(mcp_registry=None)
                    
                    # Mask the alert data using configured pattern group
                    alert_data.data = masking_service.mask_alert_data(
                        alert_data.data,
                        pattern_group=settings.alert_data_masking_pattern_group
                    )
                    
                    logger.debug(f"Alert data masking applied with pattern group: {settings.alert_data_masking_pattern_group}")
                    
                except Exception as mask_error:
                    # Log error but continue processing - fail-open for reliability
                    logger.error(f"Failed to apply alert data masking: {mask_error}", exc_info=True)
                    logger.warning("Continuing with unmasked alert data due to masking error")
            else:
                logger.debug("Alert data masking is disabled")
            
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
        
        # Additional business logic validation for alert_type (if provided)
        if alert_data.alert_type is not None and len(alert_data.alert_type.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid alert_type",
                    "message": "alert_type cannot be empty or contain only whitespace (omit field to use default)",
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
        
        # Get default alert type from chain registry
        from tarsy.main import alert_service
        
        if alert_service is None:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        default_alert_type = alert_service.chain_registry.get_default_alert_type()
        
        # Transform API alert to ProcessingAlert (adds metadata, keeps data pristine)
        processing_alert = ProcessingAlert.from_api_alert(alert_data, default_alert_type)
        
        # Generate session_id BEFORE starting background processing
        session_id = str(uuid.uuid4())
        
        # Extract author from oauth2-proxy headers
        author = extract_author_from_request(request)
        
        # Create ChainContext for processing  
        from tarsy.models.processing_context import ChainContext
        
        # Create ChainContext from ProcessingAlert
        alert_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=session_id,
            current_stage_name="initializing",  # Will be updated to actual stage names from config during execution
            author=author  # Pass author to context
        )
        
        # Get chain definition for this alert type to create session record
        try:
            chain_definition = alert_service.get_chain_for_alert(processing_alert.alert_type)
        except ValueError as e:
            logger.error(f"Chain selection failed: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid alert type",
                    "message": str(e),
                    "field": "alert_type"
                }
            ) from e
        
        # Check queue size limit (if configured)
        from tarsy.services.history_service import get_history_service
        
        history_service = get_history_service()
        if settings.max_queue_size is not None and history_service:
            pending_count = history_service.count_pending_sessions()
            if pending_count >= settings.max_queue_size:
                raise HTTPException(
                    status_code=429,  # Too Many Requests
                    detail={
                        "error": "Queue full",
                        "message": f"Alert queue is full ({pending_count}/{settings.max_queue_size}). Please try again later.",
                        "queue_size": pending_count,
                        "max_queue_size": settings.max_queue_size
                    }
                )
        
        # Create session in database BEFORE returning to client
        # This ensures the session exists when the frontend tries to fetch it
        # Session is created in PENDING state - SessionClaimWorker will claim it
        session_created = alert_service.session_manager.create_chain_history_session(
            alert_context, 
            chain_definition
        )
        
        if not session_created:
            logger.error(f"Failed to create session {session_id} in database")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Session creation failed",
                    "message": "Failed to create session record in database",
                    "support_info": "Please check the server logs or contact support if this persists"
                }
            )
        
        logger.info(f"Session {session_id} created in PENDING state, waiting for worker to claim")
        logger.info(f"Alert submitted with session_id: {session_id}")
        
        # Return session_id - session is guaranteed to exist in database
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
        ) from e