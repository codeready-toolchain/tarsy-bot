"""
JWT Authentication Dependencies

Universal JWT authentication dependencies for HTTP and WebSocket endpoints.
Provides token verification with consistent error handling across all protected endpoints.
"""

import functools
import logging
from typing import Annotated, Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request, status, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tarsy.config.settings import get_settings
from tarsy.services.jwt_service import JWTService

# HTTPBearer security scheme for HTTP endpoints (optional for hybrid auth)
security = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)


def _extract_cookie_token_from_websocket(websocket: WebSocket) -> Optional[str]:
    """Extract access_token from WebSocket Cookie header."""
    cookie_header = websocket.headers.get("cookie")
    if cookie_header:
        cookies = {}
        for cookie_part in cookie_header.split(";"):
            if "=" in cookie_part:
                key, value = cookie_part.strip().split("=", 1)
                cookies[key] = value
        return cookies.get("access_token")
    return None


def _extract_bearer_token_from_websocket(websocket: WebSocket) -> Optional[str]:
    """Extract Bearer token from WebSocket Authorization header."""
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix
    return None


def _extract_token_from_request(
    request: Request, 
    token: Optional[HTTPAuthorizationCredentials]
) -> Optional[str]:
    """
    Extract JWT token from HTTP request (Bearer token or cookies).
    
    Priority order:
    1. Authorization: Bearer header
    2. access_token cookie
    
    Returns:
        Token string if found, None otherwise
    """
    # Try Bearer token first
    if token:
        return token.credentials
    
    # Try cookie second
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    
    return None


@functools.lru_cache(maxsize=1)
def get_jwt_service() -> JWTService:
    """
    Get JWT service instance configured with current settings.
    
    Uses LRU cache to ensure singleton behavior - RSA keys are loaded once and reused.
    This prevents expensive key reloading on every service instantiation.
    
    Note for testing: Call clear_jwt_service_cache() when tests modify settings
    to ensure test isolation.
    """
    return JWTService(get_settings())


def clear_jwt_service_cache() -> None:
    """
    Clear the JWT service cache.
    
    Should be called in test fixtures when settings are modified to ensure
    the cached JWT service reflects updated configuration.
    """
    get_jwt_service.cache_clear()


async def verify_jwt_token(
    request: Request,
    token: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    jwt_service: Annotated[JWTService, Depends(get_jwt_service)]
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
    extracted_token = _extract_token_from_request(request, token)
    
    if extracted_token:
        try:
            payload = jwt_service.verify_jwt_token(extracted_token)
            return payload
        except HTTPException as e:
            # Handle specific JWT validation errors
            if token:
                # If Bearer token is present but invalid, don't fall back
                raise
            else:
                # Invalid cookie - provide user-friendly message
                logger.warning(f"Invalid authentication cookie: {e.detail}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication cookie expired or invalid"
                )
        except Exception:
            # Convert other exceptions to HTTPException
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed"
            )
    
    # No valid authentication found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide Bearer token or valid session cookie"
    )


async def verify_jwt_token_websocket(
    websocket: WebSocket,
    jwt_service: Annotated[JWTService, Depends(get_jwt_service)]
) -> Optional[Dict[str, Any]]:
    """
    WebSocket JWT verification supporting browser and programmatic authentication.
    
    Browsers send cookies during WebSocket handshake, enabling secure authentication.
    Programmatic clients can use Authorization headers.
    
    Authentication priority order:
    1. HTTP-only cookies (access_token cookie) - for browser clients
    2. Authorization: Bearer <token> header - for programmatic clients
    
    Args:
        websocket: WebSocket connection instance
        jwt_service: JWT service for token validation
        
    Returns:
        Dict containing JWT payload if valid, None if authentication fails
    """
    # Try cookies first (most secure for browser clients)
    cookie_token = _extract_cookie_token_from_websocket(websocket)
    if cookie_token:
        try:
            payload = jwt_service.verify_jwt_token(cookie_token)
            logger.debug("WebSocket authenticated via cookie")
            return payload
        except Exception as e:
            logger.warning(f"WebSocket cookie authentication failed: {e}")
    
    # Try Authorization header second (for programmatic clients)
    bearer_token = _extract_bearer_token_from_websocket(websocket)
    if bearer_token:
        try:
            payload = jwt_service.verify_jwt_token(bearer_token)
            logger.debug("WebSocket authenticated via Authorization header")
            return payload
        except Exception as e:
            logger.warning(f"WebSocket Authorization header authentication failed: {e}")
    
    # No valid authentication found
    logger.warning("WebSocket authentication failed: no valid token found in cookies or headers")
    return None
