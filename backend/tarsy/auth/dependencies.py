"""
JWT Authentication Dependencies

Universal JWT authentication dependencies for HTTP and WebSocket endpoints.
Provides token verification with consistent error handling across all protected endpoints.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request, status, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tarsy.config.settings import get_settings
from tarsy.services.jwt_service import JWTService

# HTTPBearer security scheme for HTTP endpoints (optional for hybrid auth)
security = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)


def get_jwt_service() -> JWTService:
    """Get JWT service instance configured with current settings."""
    return JWTService(get_settings())


async def verify_jwt_token(
    request: Request,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> Dict[str, Any]:
    """
    Hybrid JWT verification supporting both Bearer tokens and cookies.
    
    Priority Order:
    1. Authorization: Bearer <token> (for service accounts and API clients)
    2. access_token cookie (for browser-based user authentication)
    
    This enables the same endpoints to serve both:
    - Service accounts using Bearer tokens
    - Web users using secure HTTP-only cookies
    
    Args:
        request: FastAPI request object to access cookies
        token: Optional HTTP Authorization credentials from Bearer token
        jwt_service: JWT service for token validation
        
    Returns:
        Dict containing JWT payload with user/service account information
        
    Raises:
        HTTPException: 401 if no valid authentication found
    """
    # Try Bearer token first (service accounts, API clients)
    if token:
        try:
            payload = jwt_service.verify_jwt_token(token.credentials)
            return payload
        except HTTPException:
            # If Bearer token is present but invalid, don't fall back to cookie
            raise
    
    # Fall back to cookie authentication (web users)
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        try:
            payload = jwt_service.verify_jwt_token(cookie_token)
            return payload
        except HTTPException as e:
            # Clear invalid cookie and require re-authentication
            logger.warning(f"Invalid authentication cookie, clearing: {e.detail}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication cookie expired or invalid"
            )
    
    # No valid authentication found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide Bearer token or valid session cookie"
    )


async def verify_jwt_token_websocket(
    _websocket: WebSocket,
    token: str = Query(..., description="JWT token for WebSocket authentication"),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> Optional[Dict[str, Any]]:
    """
    WebSocket JWT verification.
    
    Note: WebSockets cannot use HTTP-only cookies, so they must use token query parameter.
    Frontend should extract token from cookie using server-side helper endpoint if needed.
    
    Args:
        websocket: WebSocket connection instance
        token: JWT token from query parameter
        jwt_service: JWT service for token validation
        
    Returns:
        Dict containing JWT payload if valid, None if invalid
    """
    try:
        payload = jwt_service.verify_jwt_token(token)
        return payload
    except Exception as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        return None
