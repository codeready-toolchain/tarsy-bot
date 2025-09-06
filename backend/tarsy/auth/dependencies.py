"""
JWT Authentication Dependencies

Universal JWT authentication dependencies for HTTP and WebSocket endpoints.
Provides token verification with consistent error handling across all protected endpoints.
"""

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tarsy.config.settings import get_settings
from tarsy.services.jwt_service import JWTService

# HTTPBearer security scheme for HTTP endpoints
security = HTTPBearer()


def get_jwt_service() -> JWTService:
    """Get JWT service instance configured with current settings."""
    return JWTService(get_settings())


async def verify_jwt_token(
    token: HTTPAuthorizationCredentials = Depends(security),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> Dict[str, Any]:
    """
    Verify JWT token for HTTP endpoints.
    
    This dependency should be used for all protected HTTP endpoints.
    It extracts the JWT token from the Authorization header and validates it.
    
    Args:
        token: HTTP Authorization credentials from Bearer token
        jwt_service: JWT service for token validation
        
    Returns:
        Dict containing JWT payload with user/service account information
        
    Raises:
        HTTPException: 401 if token is invalid, missing, or expired
    """
    try:
        payload = jwt_service.verify_jwt_token(token.credentials)
        return payload
    except HTTPException:
        # Re-raise JWT service HTTP exceptions (already have proper status codes)
        raise
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed"
        )


async def verify_jwt_token_websocket(
    token: str = Query(..., description="JWT token for authentication"),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token for WebSocket endpoints.
    
    This dependency should be used for WebSocket endpoints that require authentication.
    Returns None if token is invalid instead of raising an exception, allowing
    the WebSocket handler to close the connection gracefully.
    
    Args:
        token: JWT token from query parameter
        jwt_service: JWT service for token validation
        
    Returns:
        Dict containing JWT payload if valid, None if invalid
    """
    try:
        payload = jwt_service.verify_jwt_token(token)
        return payload
    except Exception:
        # Return None for any validation error - WebSocket handler should close connection
        return None
