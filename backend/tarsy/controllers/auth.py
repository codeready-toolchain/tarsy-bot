"""
Authentication controller for GitHub OAuth and JWT token management.

Handles OAuth flow, membership validation, and JWT token issuance.
"""

from uuid import uuid4
import logging
import json
import base64
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from tarsy.config.settings import get_settings
from tarsy.database.dependencies import get_session  
from tarsy.repositories.oauth_state_repository import OAuthStateRepository
from tarsy.services.jwt_service import JWTService
from tarsy.services.github_service import validate_github_membership
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

# Hardcoded dev user (simple, no overrides)
DEV_USER = {
    "id": 999999,
    "login": "tarsy-dev-user", 
    "email": "dev@tarsy-local.invalid",
    "avatar_url": "https://github.com/github.png"
}


def _set_auth_cookie(response: Response, jwt_token: str) -> None:
    """Set secure HTTP-only authentication cookie."""
    settings = get_settings()
    
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,  # Prevents JavaScript access (XSS protection)
        secure=not settings.dev_mode,  # HTTPS only in production
        samesite="strict",  # CSRF protection
        max_age=7 * 24 * 60 * 60,  # 7 days (matches JWT expiry)
        path="/",  # Available to all paths
        domain=settings.cookie_domain  # Cross-subdomain support if configured
    )


@router.get("/login")
async def github_login(
    session: Annotated[Session, Depends(get_session)],
    redirect_url: str = Query(default="http://localhost:5173/", description="URL to redirect after successful authentication")
):
    """Start GitHub OAuth flow with state-encoded redirect support."""
    settings = get_settings()
    
    # Validate redirect URL based on environment
    if settings.dev_mode:
        # Dev mode: allow any localhost port
        if not re.match(r'^https?://localhost:\d+/?.*', redirect_url):
            raise HTTPException(400, "Dev mode: redirect URL must be localhost")
    else:
        # Production: only allow configured frontend URL
        if not redirect_url.startswith(settings.frontend_url):
            raise HTTPException(400, f"Production mode: redirect URL must start with {settings.frontend_url}")
    
    if settings.dev_mode:
        # Dev mode: Skip GitHub, redirect directly to callback with encoded state
        logger.warning("🚨 DEV MODE: Using insecure development authentication! 🚨")
        
        # Encode redirect URL into state for dev callback
        state_data = {
            "csrf_token": "dev_fake_state",
            "redirect_url": redirect_url
        }
        encoded_state = base64.urlsafe_b64encode(
            json.dumps(state_data).encode()
        ).decode()
        
        return RedirectResponse(f"/auth/callback?code=dev_fake_code&state={encoded_state}")
    
    # Production OAuth flow
    # Generate and store OAuth state for CSRF protection
    csrf_token = str(uuid4())
    expires_at = now_us() + (settings.oauth_state_ttl_minutes * 60_000_000)  # Convert minutes to microseconds
    
    # Encode redirect URL into OAuth state parameter
    state_data = {
        "csrf_token": csrf_token,
        "redirect_url": redirect_url
    }
    encoded_state = base64.urlsafe_b64encode(
        json.dumps(state_data).encode()
    ).decode()
    
    # Store only CSRF token in database (not full state data)
    oauth_repo = OAuthStateRepository(session)
    oauth_repo.create_state(csrf_token, expires_at)
    
    # Build GitHub OAuth URL with encoded state using requests-oauthlib
    from requests_oauthlib import OAuth2Session
    
    oauth = OAuth2Session(
        client_id=settings.github_client_id,
        redirect_uri=f"{settings.backend_url}/auth/callback",
        scope=["user:email", "read:org"]
    )
    
    authorization_url, _ = oauth.authorization_url(
        settings.github_oauth_authorize_url,
        state=encoded_state
    )
    
    return RedirectResponse(authorization_url)


@router.get("/callback") 
async def github_callback(
    code: str, 
    state: str,
    response: Response,
    session: Annotated[Session, Depends(get_session)]
):
    """Handle GitHub OAuth callback with state-encoded redirect support."""
    settings = get_settings()
    
    # Decode state parameter to extract redirect URL and CSRF token
    try:
        state_data = json.loads(
            base64.urlsafe_b64decode(state.encode()).decode()
        )
        csrf_token = state_data["csrf_token"]
        redirect_url = state_data["redirect_url"]
    except Exception:
        raise HTTPException(400, "Invalid OAuth state parameter")
    
    if settings.dev_mode:
        # Dev mode: Use hardcoded user data, generate real JWT
        logger.warning("🚨 DEV MODE: Generating JWT with fake user data! 🚨")
        
        jwt_service = JWTService(settings)
        jwt_token = jwt_service.create_user_jwt_token(
            user_id=str(DEV_USER["id"]),
            username=DEV_USER["login"],
            email=DEV_USER["email"], 
            avatar_url=DEV_USER["avatar_url"]
        )
        
        # Create redirect response and set cookie on it
        redirect_response = RedirectResponse(redirect_url)
        _set_auth_cookie(redirect_response, jwt_token)
        
        return redirect_response
    
    # Production OAuth flow
    try:
        oauth_repo = OAuthStateRepository(session)
        
        # Validate OAuth CSRF token exists in database
        oauth_state = oauth_repo.get_state(csrf_token)
        if not oauth_state or oauth_state.expires_at < now_us():
            raise HTTPException(400, "Invalid or expired OAuth state")
        
        # Clean up used state
        oauth_repo.delete_state(csrf_token)
        
        # Exchange code for access token using requests-oauthlib
        from requests_oauthlib import OAuth2Session
        
        logger.debug("Exchanging OAuth code for access token using requests-oauthlib")
        try:
            oauth = OAuth2Session(
                client_id=settings.github_client_id,
                redirect_uri=f"{settings.backend_url}/auth/callback"
            )
            
            # Exchange code for token
            token_response = oauth.fetch_token(
                token_url=settings.github_oauth_token_url,
                code=code,
                client_secret=settings.github_client_secret
            )
        except Exception as e:
            logger.error(f"GitHub OAuth token exchange failed: {e}")
            raise HTTPException(500, f"GitHub OAuth token exchange failed: {str(e)}")
        
        github_access_token = token_response['access_token']
        
        # Get user data and validate membership
        from github import Github, Auth
        auth = Auth.Token(github_access_token)
        
        # Use configurable GitHub API base URL for GitHub Enterprise support
        github_api_url = settings.github_base_url.replace("github.com", "api.github.com")
        if "github.com" not in settings.github_base_url:
            # GitHub Enterprise format: https://github.company.com -> https://github.company.com/api/v3
            github_api_url = f"{settings.github_base_url.rstrip('/')}/api/v3"
        
        # Debug logging for GitHub API URL
        logger.debug(f"GitHub API parameters: base_url={github_api_url}, access_token=***")
        
        g = Github(auth=auth, base_url=github_api_url)
        github_user = g.get_user()
        
        # Validate org/team membership (raises HTTPException if invalid)
        await validate_github_membership(github_access_token, github_user.login)
        
        # Generate JWT token with user claims
        jwt_service = JWTService(settings)
        jwt_token = jwt_service.create_user_jwt_token(
            user_id=str(github_user.id),
            username=github_user.login,
            email=github_user.email or "",  # Handle None email
            avatar_url=github_user.avatar_url or ""  # Handle None avatar_url
        )
        
        # Create redirect response and set cookie on it
        redirect_response = RedirectResponse(redirect_url)
        _set_auth_cookie(redirect_response, jwt_token)
        
        return redirect_response
        
    except HTTPException:
        raise  # Re-raise validation errors (403, etc.)
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(500, "OAuth callback failed")


@router.post("/logout")
async def logout(response: Response):
    """Clear authentication cookie and log out user."""
    settings = get_settings()
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="strict",
        domain=settings.cookie_domain  # Must match domain used when setting cookie
    )
    return {"message": "Successfully logged out"}


@router.get("/token")
async def get_token_from_cookie(request: Request):
    """
    Extract JWT token from HTTP-only cookie for WebSocket connections.
    
    Frontend can call this endpoint to get the token for WebSocket authentication
    since WebSockets cannot access HTTP-only cookies directly.
    """
    cookie_token = request.cookies.get("access_token")
    if not cookie_token:
        raise HTTPException(401, "No authentication cookie found")
    
    # Verify token is valid before returning
    jwt_service = JWTService(get_settings())
    try:
        payload = jwt_service.verify_jwt_token(cookie_token)
        return {"access_token": cookie_token}
    except HTTPException:
        raise HTTPException(401, "Authentication cookie is invalid or expired")