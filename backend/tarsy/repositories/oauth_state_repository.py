"""
OAuth state repository for database operations.

Provides CRUD operations for OAuth state management with automatic cleanup.
"""

from typing import Optional

from sqlalchemy import delete, select
from sqlmodel import Session

from tarsy.models.db_models import OAuthState
from tarsy.utils.timestamp import now_us


class OAuthStateRepository:
    """Repository for OAuth state database operations."""
    
    def __init__(self, session: Session):
        """Initialize repository with database session."""
        self.session = session
    
    def create_state(self, state: str, expires_at: int) -> OAuthState:
        """
        Create a new OAuth state.
        
        Args:
            state: OAuth state parameter for CSRF protection
            expires_at: Expiration timestamp in microseconds since epoch
            
        Returns:
            Created OAuthState instance
        """
        oauth_state = OAuthState(
            state=state,
            created_at=now_us(),
            expires_at=expires_at
        )
        self.session.add(oauth_state)
        self.session.commit()
        return oauth_state
    
    def get_state(self, state: str) -> Optional[OAuthState]:
        """
        Get OAuth state by state parameter.
        
        Args:
            state: OAuth state parameter
            
        Returns:
            OAuthState instance if found, None otherwise
        """
        return self.session.exec(
            select(OAuthState).where(OAuthState.state == state)
        ).first()
    
    def delete_state(self, state: str) -> None:
        """
        Delete OAuth state.
        
        Args:
            state: OAuth state parameter to delete
        """
        self.session.exec(
            delete(OAuthState).where(OAuthState.state == state)
        )
        self.session.commit()
    
    def cleanup_expired_states(self) -> int:
        """
        Clean up expired OAuth states and return count of deleted records.
        
        Returns:
            Number of deleted expired states
        """
        current_time = now_us()
        result = self.session.exec(
            delete(OAuthState).where(OAuthState.expires_at < current_time)
        )
        self.session.commit()
        return result.rowcount or 0
