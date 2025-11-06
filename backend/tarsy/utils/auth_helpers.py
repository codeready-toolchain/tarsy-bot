"""
Authentication helper utilities for FastAPI controllers.

Provides helper functions for extracting user information from request headers,
particularly oauth2-proxy headers for user identification.
"""

from fastapi import Request


def extract_author_from_request(request: Request) -> str:
    """
    Extract author (user identifier) from oauth2-proxy headers.
    
    oauth2-proxy injects X-Forwarded-User and X-Forwarded-Email headers when
    pass_user_headers=true (OAuth flow). For JWT-authenticated API clients,
    oauth2-proxy validates but doesn't inject user headers.
    
    Priority:
    1. X-Forwarded-User (GitHub username, etc.)
    2. X-Forwarded-Email (user's email address)
    3. "api-client" (default for JWT/API clients without user headers)
    
    Args:
        request: FastAPI Request object containing headers
        
    Returns:
        Author identifier string (username, email, or "api-client")
        
    Examples:
        >>> # OAuth user with username
        >>> request.headers = {"X-Forwarded-User": "github-user"}
        >>> extract_author_from_request(request)
        "github-user"
        
        >>> # OAuth user with only email
        >>> request.headers = {"X-Forwarded-Email": "user@example.com"}
        >>> extract_author_from_request(request)
        "user@example.com"
        
        >>> # API client (no headers)
        >>> request.headers = {}
        >>> extract_author_from_request(request)
        "api-client"
    """
    author = request.headers.get("X-Forwarded-User") or request.headers.get(
        "X-Forwarded-Email"
    )
    
    # Strip whitespace and check if empty
    if author:
        author = author.strip()
    
    # If no user headers present or empty after stripping, default to api-client
    if not author:
        author = "api-client"
    
    return author

