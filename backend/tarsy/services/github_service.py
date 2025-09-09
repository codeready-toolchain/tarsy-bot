"""
GitHub integration service for organization and team membership validation.

Provides OAuth and membership validation functionality using PyGithub.
"""

import asyncio

from github import Github
from github.GithubException import GithubException
from fastapi import HTTPException, status

from tarsy.config.settings import get_settings
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


def _create_github_client(github_access_token: str, settings) -> Github:
    """Create a GitHub client with proper authentication and base URL."""
    from github import Auth
    auth = Auth.Token(github_access_token)
    
    # Use configurable GitHub API base URL for GitHub Enterprise support
    github_api_url = settings.github_base_url.replace("github.com", "api.github.com")
    if "github.com" not in settings.github_base_url:
        # GitHub Enterprise format: https://github.company.com -> https://github.company.com/api/v3
        github_api_url = f"{settings.github_base_url.rstrip('/')}/api/v3"
    
    return Github(auth=auth, base_url=github_api_url)


def _get_authenticated_user(github_client: Github):
    """Get the authenticated user from GitHub API."""
    return github_client.get_user()


def _check_organization_membership(authenticated_user, github_org: str) -> bool:
    """Check if user is an active member of the organization."""
    membership = authenticated_user.get_organization_membership(github_org)
    return membership.state == "active"


def _get_user_teams(authenticated_user) -> list[str]:
    """Get list of team slugs for the authenticated user."""
    return [team_item.slug for team_item in authenticated_user.get_teams()]


async def validate_github_membership(github_access_token: str, username: str) -> None:
    """
    Validate GitHub org/team membership using PyGithub.
    
    Args:
        github_access_token: GitHub OAuth access token
        username: GitHub username to validate
        
    Raises:
        HTTPException: If validation fails or API errors occur
    """
    settings = get_settings()
    logger.info(f"Validating GitHub membership for user: {username}")
    
    try:
        # Initialize GitHub client with access token and configurable base URL
        github_client = await asyncio.to_thread(_create_github_client, github_access_token, settings)
        
        # Get the authenticated user (this is key - it uses the /user endpoint, not /users/{username})
        authenticated_user = await asyncio.to_thread(_get_authenticated_user, github_client)
        
        # Verify the authenticated user matches the requested user
        if authenticated_user.login != username:
            logger.warning(f"GitHub token mismatch: token belongs to {authenticated_user.login}, expected {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub token does not match the authenticated user"
            )
        
        # Check organization membership using authenticated user's perspective
        # This works for both public and private memberships with read:org scope
        try:
            is_org_member = await asyncio.to_thread(_check_organization_membership, authenticated_user, settings.github_org)
        except GithubException as e:
            logger.error(f"Failed to check organization membership for {username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: insufficient GitHub organization permissions"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error checking organization membership for {username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub authentication service error"
            ) from e
        
        if not is_org_member:
            logger.warning(f"User {username} is not an active member of organization {settings.github_org}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: insufficient GitHub organization permissions"
            )
        
        # Check team membership (if configured)
        if settings.github_team:
            try:
                # Check team membership from authenticated user's perspective  
                user_teams = await asyncio.to_thread(_get_user_teams, authenticated_user)
                is_team_member = settings.github_team in user_teams
                
                if not is_team_member:
                    logger.warning(f"User {username} is not a member of required team {settings.github_team}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: insufficient GitHub team permissions"
                    )
                logger.info(f"User {username} successfully validated for team {settings.github_team}")
            except GithubException as e:
                logger.error(f"Failed to check team membership for {username}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GitHub authentication configuration error"
                ) from e
            except Exception as e:
                logger.error(f"Unexpected error checking team membership for {username}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GitHub authentication service error"
                ) from e
        else:
            logger.info(f"User {username} successfully validated for organization {settings.github_org}")
                
    except GithubException as e:
        logger.error(f"GitHub API error for user {username}: status={e.status}, message={e.data}")
        if e.status == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub access token is invalid or expired"
            ) from e
        elif e.status == 404:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub authentication configuration error"
            ) from e
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub authentication service error"
            ) from e
