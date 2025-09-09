"""
GitHub integration service for organization and team membership validation.

Provides OAuth and membership validation functionality using PyGithub.
"""

from github import Github
from github.GithubException import GithubException, UnknownObjectException
from fastapi import HTTPException, status

from tarsy.config.settings import get_settings


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
    
    try:
        # Initialize GitHub client with access token and configurable base URL
        from github import Auth
        auth = Auth.Token(github_access_token)
        
        # Use configurable GitHub API base URL for GitHub Enterprise support
        github_api_url = settings.github_base_url.replace("github.com", "api.github.com")
        if "github.com" not in settings.github_base_url:
            # GitHub Enterprise format: https://github.company.com -> https://github.company.com/api/v3
            github_api_url = f"{settings.github_base_url.rstrip('/')}/api/v3"
        
        g = Github(auth=auth, base_url=github_api_url)
        
        # Get the authenticated user (this is key - it uses the /user endpoint, not /users/{username})
        authenticated_user = g.get_user()
        # Also get the specific user object for verification
        user = g.get_user(username)
        org = g.get_organization(settings.github_org)
        
        # Verify the authenticated user matches the requested user
        if authenticated_user.login != username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub token does not match the authenticated user"
            )
        
        # Check organization membership using authenticated user's perspective
        # This works for both public and private memberships with read:org scope
        try:
            membership = authenticated_user.get_organization_membership(settings.github_org)
            is_org_member = membership.state == "active"
        except Exception:
            # User is not a member or organization has restrictions
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: insufficient GitHub organization permissions"
            )
        
        if not is_org_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: insufficient GitHub organization permissions"
            )
        
        # Check team membership (if configured)
        if settings.github_team:
            try:
                # Check team membership from authenticated user's perspective  
                user_teams = [team_item.slug for team_item in authenticated_user.get_teams()]
                is_team_member = settings.github_team in user_teams
                
                if not is_team_member:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: insufficient GitHub team permissions"
                    )
                    
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GitHub authentication configuration error"
                )
                
    except GithubException as e:
        if e.status == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub access token is invalid or expired"
            )
        elif e.status == 404:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub authentication configuration error"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub authentication service error"
            )
