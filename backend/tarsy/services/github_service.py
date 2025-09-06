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
        # Initialize GitHub client with access token
        g = Github(github_access_token)
        user = g.get_user(username)
        org = g.get_organization(settings.github_org)
        
        # Check organization membership (required)
        if not org.has_in_members(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: insufficient GitHub organization permissions"
            )
        
        # Check team membership (if configured)
        if settings.github_team:
            try:
                team = org.get_team_by_slug(settings.github_team)
                if not team.has_in_members(user):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: insufficient GitHub team permissions"
                    )
            except UnknownObjectException:
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
