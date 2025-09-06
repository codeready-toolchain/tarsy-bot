"""
Authentication controller for GitHub OAuth and JWT token management.

Handles OAuth flow, membership validation, and JWT token issuance.
"""

from uuid import uuid4
import logging

from fastapi import APIRouter, Depends, HTTPException
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


@router.get("/login")
async def github_login(session: Session = Depends(get_session)):
    """Start GitHub OAuth flow or dev mode login."""
    settings = get_settings()
    
    if settings.dev_mode:
        # Dev mode: Skip GitHub, redirect directly to callback with fake params
        logger.warning("🚨 DEV MODE: Using insecure development authentication! 🚨")
        return RedirectResponse(f"/auth/callback?code=dev_fake_code&state=dev_fake_state")
    
    # Production OAuth flow
    # Generate and store OAuth state for CSRF protection using repository
    state = str(uuid4())
    expires_at = now_us() + (settings.oauth_state_ttl_minutes * 60_000_000)  # Convert minutes to microseconds
    
    oauth_repo = OAuthStateRepository(session)
    oauth_repo.create_state(state, expires_at)
    
    # Build GitHub OAuth URL using authlib's URL builder
    from authlib.integrations.httpx_client import AsyncOAuth2Client
    
    oauth_client = AsyncOAuth2Client(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret
    )
    
    authorization_url, _ = oauth_client.create_authorization_url(
        url=settings.github_oauth_authorize_url,
        redirect_uri=f"{settings.backend_url}/auth/callback",
        scope="user:email,read:org",
        state=state
    )
    
    return RedirectResponse(authorization_url)


@router.get("/callback") 
async def github_callback(
    code: str, 
    state: str, 
    session: Session = Depends(get_session)
):
    """Handle GitHub OAuth callback or dev mode callback."""
    settings = get_settings()
    
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
        
        return {"jwt_token": jwt_token}
    
    # Production OAuth flow
    try:
        oauth_repo = OAuthStateRepository(session)
        
        # Validate OAuth state to prevent CSRF
        oauth_state = oauth_repo.get_state(state)
        if not oauth_state or oauth_state.expires_at < now_us():
            raise HTTPException(400, "Invalid or expired OAuth state")
        
        # Clean up used state
        oauth_repo.delete_state(state)
        
        # Exchange code for access token using authlib
        from authlib.integrations.httpx_client import AsyncOAuth2Client
        
        oauth_client = AsyncOAuth2Client(
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret
        )
        
        token_response = await oauth_client.fetch_token(
            token_url=settings.github_oauth_token_url,
            code=code,
            redirect_uri=f"{settings.backend_url}/auth/callback"
        )
        
        github_access_token = token_response['access_token']
        
        # Get user data and validate membership
        from github import Github, Auth
        auth = Auth.Token(github_access_token)
        
        # Use configurable GitHub API base URL for GitHub Enterprise support
        github_api_url = settings.github_base_url.replace("github.com", "api.github.com")
        if "github.com" not in settings.github_base_url:
            # GitHub Enterprise format: https://github.company.com -> https://github.company.com/api/v3
            github_api_url = f"{settings.github_base_url.rstrip('/')}/api/v3"
        
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
        
        return {"jwt_token": jwt_token}
        
    except HTTPException:
        raise  # Re-raise validation errors (403, etc.)
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(500, "OAuth callback failed")