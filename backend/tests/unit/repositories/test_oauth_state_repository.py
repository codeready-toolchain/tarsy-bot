"""
Unit tests for OAuth state repository.

Tests CRUD operations for OAuth state management, expiration handling,
and cleanup functionality for CSRF protection.
"""

from unittest.mock import Mock, patch

import pytest
from sqlmodel import Session

from tarsy.repositories.oauth_state_repository import OAuthStateRepository
from tarsy.models.db_models import OAuthState


@pytest.fixture
def mock_session():
    """Create mock SQLModel session."""
    return Mock(spec=Session)


@pytest.fixture
def oauth_repo(mock_session):
    """Create OAuth state repository with mock session."""
    return OAuthStateRepository(mock_session)


@pytest.fixture
def sample_oauth_state():
    """Create sample OAuth state for testing."""
    return OAuthState(
        state="test_state_123",
        created_at=1609459200_000_000,  # 2021-01-01 00:00:00 UTC in microseconds
        expires_at=1609459800_000_000   # 2021-01-01 00:10:00 UTC in microseconds (10 minutes later)
    )


@pytest.mark.unit
class TestOAuthStateCreation:
    """Test OAuth state creation operations."""
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_create_state_success(self, mock_now_us, oauth_repo, mock_session):
        """Test successful OAuth state creation."""
        # Mock current time
        mock_now_us.return_value = 1609459200_000_000  # 2021-01-01 00:00:00 UTC
        
        # Test creation
        result = oauth_repo.create_state("test_state_123", 1609459800_000_000)
        
        # Verify the created object
        assert isinstance(result, OAuthState)
        assert result.state == "test_state_123"
        assert result.created_at == 1609459200_000_000
        assert result.expires_at == 1609459800_000_000
        
        # Verify session operations
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify the object added to session
        added_object = mock_session.add.call_args[0][0]
        assert isinstance(added_object, OAuthState)
        assert added_object.state == "test_state_123"
    
    def test_create_state_with_long_state_value(self, oauth_repo, mock_session):
        """Test OAuth state creation with very long state value."""
        long_state = "x" * 1000  # Very long state
        expires_at = 1609459800_000_000
        
        result = oauth_repo.create_state(long_state, expires_at)
        
        assert result.state == long_state
        assert result.expires_at == expires_at
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    def test_create_state_with_unicode_characters(self, oauth_repo, mock_session):
        """Test OAuth state creation with unicode characters."""
        unicode_state = "tëst_ståte_üñiçødé"
        expires_at = 1609459800_000_000
        
        result = oauth_repo.create_state(unicode_state, expires_at)
        
        assert result.state == unicode_state
        assert result.expires_at == expires_at
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    def test_create_state_session_error(self, oauth_repo, mock_session):
        """Test OAuth state creation with session error."""
        # Mock session commit to raise exception
        mock_session.commit.side_effect = Exception("Database error")
        
        # Should re-raise the exception
        with pytest.raises(Exception, match="Database error"):
            oauth_repo.create_state("test_state", 1609459800_000_000)
        
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.unit
class TestOAuthStateRetrieval:
    """Test OAuth state retrieval operations."""
    
    def test_get_state_success(self, oauth_repo, mock_session, sample_oauth_state):
        """Test successful OAuth state retrieval."""
        # Mock session exec to return the state
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_oauth_state
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.get_state("test_state_123")
        
        assert result == sample_oauth_state
        assert result.state == "test_state_123"
        
        # Verify query was executed
        mock_session.exec.assert_called_once()
        # Get the query argument
        query_arg = mock_session.exec.call_args[0][0]
        # Verify it's a select query - we can't easily test the exact query structure
        assert str(query_arg).startswith("SELECT")
    
    def test_get_state_not_found(self, oauth_repo, mock_session):
        """Test OAuth state retrieval when state doesn't exist."""
        # Mock session exec to return None (not found)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.get_state("nonexistent_state")
        
        assert result is None
        mock_session.exec.assert_called_once()
    
    def test_get_state_with_special_characters(self, oauth_repo, mock_session):
        """Test OAuth state retrieval with special characters in state."""
        special_state = "state!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        # Create expected OAuth state
        expected_state = OAuthState(
            state=special_state,
            created_at=1609459200_000_000,
            expires_at=1609459800_000_000
        )
        
        # Mock session exec to return the state
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = expected_state
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.get_state(special_state)
        
        assert result == expected_state
        assert result.state == special_state
        mock_session.exec.assert_called_once()
    
    def test_get_state_session_error(self, oauth_repo, mock_session):
        """Test OAuth state retrieval with session error."""
        # Mock session exec to raise exception
        mock_session.exec.side_effect = Exception("Database query error")
        
        # Should re-raise the exception
        with pytest.raises(Exception, match="Database query error"):
            oauth_repo.get_state("test_state")
        
        mock_session.exec.assert_called_once()


@pytest.mark.unit
class TestOAuthStateDeletion:
    """Test OAuth state deletion operations."""
    
    def test_delete_state_success(self, oauth_repo, mock_session):
        """Test successful OAuth state deletion."""
        oauth_repo.delete_state("test_state_123")
        
        # Verify delete query was executed
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify it's a delete query
        query_arg = mock_session.exec.call_args[0][0]
        assert "DELETE" in str(query_arg) or hasattr(query_arg, 'where')  # SQLAlchemy delete query
    
    def test_delete_state_not_exists(self, oauth_repo, mock_session):
        """Test OAuth state deletion when state doesn't exist."""
        # Mock session exec to return result indicating no rows affected
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_session.exec.return_value = mock_result
        
        # Should not raise exception even if state doesn't exist
        oauth_repo.delete_state("nonexistent_state")
        
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
    
    def test_delete_state_with_unicode(self, oauth_repo, mock_session):
        """Test OAuth state deletion with unicode characters."""
        unicode_state = "ståte_tëst_üñiçødé"
        
        oauth_repo.delete_state(unicode_state)
        
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
    
    def test_delete_state_session_error(self, oauth_repo, mock_session):
        """Test OAuth state deletion with session error."""
        # Mock session commit to raise exception
        mock_session.commit.side_effect = Exception("Database commit error")
        
        # Should re-raise the exception
        with pytest.raises(Exception, match="Database commit error"):
            oauth_repo.delete_state("test_state")
        
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.unit
class TestOAuthStateCleanup:
    """Test OAuth state cleanup operations."""
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_cleanup_expired_states_success(self, mock_now_us, oauth_repo, mock_session):
        """Test successful cleanup of expired OAuth states."""
        # Mock current time (states expired before this time should be deleted)
        current_time = 1609459800_000_000  # 2021-01-01 00:10:00 UTC
        mock_now_us.return_value = current_time
        
        # Mock session exec to return result with 3 deleted rows
        mock_result = Mock()
        mock_result.rowcount = 3
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.cleanup_expired_states()
        
        assert result == 3
        
        # Verify query and commit were called
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify it's a delete query
        query_arg = mock_session.exec.call_args[0][0]
        assert "DELETE" in str(query_arg) or hasattr(query_arg, 'where')
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_cleanup_expired_states_none_expired(self, mock_now_us, oauth_repo, mock_session):
        """Test cleanup when no OAuth states are expired."""
        # Mock current time
        current_time = 1609459200_000_000  # Early time, no states expired
        mock_now_us.return_value = current_time
        
        # Mock session exec to return result with 0 deleted rows
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.cleanup_expired_states()
        
        assert result == 0
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_cleanup_expired_states_rowcount_none(self, mock_now_us, oauth_repo, mock_session):
        """Test cleanup when rowcount is None (some database drivers)."""
        # Mock current time
        current_time = 1609459800_000_000
        mock_now_us.return_value = current_time
        
        # Mock session exec to return result with None rowcount
        mock_result = Mock()
        mock_result.rowcount = None  # Some database drivers return None
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.cleanup_expired_states()
        
        assert result == 0  # Should default to 0 when rowcount is None
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_cleanup_expired_states_large_cleanup(self, mock_now_us, oauth_repo, mock_session):
        """Test cleanup with large number of expired states."""
        # Mock current time
        current_time = 1609459800_000_000
        mock_now_us.return_value = current_time
        
        # Mock session exec to return result with large number of deleted rows
        mock_result = Mock()
        mock_result.rowcount = 10000
        mock_session.exec.return_value = mock_result
        
        result = oauth_repo.cleanup_expired_states()
        
        assert result == 10000
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_cleanup_expired_states_session_error(self, mock_now_us, oauth_repo, mock_session):
        """Test cleanup with session error."""
        # Mock current time
        current_time = 1609459800_000_000
        mock_now_us.return_value = current_time
        
        # Mock session commit to raise exception
        mock_session.commit.side_effect = Exception("Database cleanup error")
        
        # Should return 0 instead of raising exception (graceful error handling)
        result = oauth_repo.cleanup_expired_states()
        
        assert result == 0
        mock_session.exec.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_called_once()


@pytest.mark.unit
class TestOAuthStateRepositoryIntegration:
    """Test realistic integration scenarios."""
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_complete_oauth_flow_simulation(self, mock_now_us, oauth_repo, mock_session):
        """Test complete OAuth state lifecycle: create → get → delete."""
        # Mock current time
        mock_now_us.return_value = 1609459200_000_000  # 2021-01-01 00:00:00 UTC
        
        # 1. Create OAuth state
        expires_at = 1609459800_000_000  # 10 minutes later
        created_state = oauth_repo.create_state("oauth_flow_state", expires_at)
        
        assert created_state.state == "oauth_flow_state"
        assert created_state.expires_at == expires_at
        
        # 2. Simulate retrieval (mock the state being found)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = created_state
        mock_session.exec.return_value = mock_result
        
        retrieved_state = oauth_repo.get_state("oauth_flow_state")
        assert retrieved_state == created_state
        
        # 3. Delete the state after use
        oauth_repo.delete_state("oauth_flow_state")
        
        # Verify all operations were called
        assert mock_session.add.call_count == 1
        assert mock_session.commit.call_count == 2  # Once for create, once for delete
        assert mock_session.exec.call_count == 2   # Once for get, once for delete
    
    @patch('tarsy.repositories.oauth_state_repository.now_us')
    def test_expired_state_cleanup_scenario(self, mock_now_us, oauth_repo, mock_session):
        """Test realistic expired state cleanup scenario."""
        # Time progression simulation
        initial_time = 1609459200_000_000    # 2021-01-01 00:00:00 UTC
        cleanup_time = 1609459800_000_000     # 2021-01-01 00:10:00 UTC (10 minutes later)
        
        # 1. Create states at initial time
        mock_now_us.return_value = initial_time
        
        # Create multiple states with different expiration times
        oauth_repo.create_state("state1", initial_time + 300_000_000)  # Expires in 5 minutes
        oauth_repo.create_state("state2", initial_time + 600_000_000)  # Expires in 10 minutes
        oauth_repo.create_state("state3", initial_time + 900_000_000)  # Expires in 15 minutes
        
        # 2. Advance time to cleanup time (10 minutes later)
        mock_now_us.return_value = cleanup_time
        
        # 3. Cleanup expired states
        # Mock cleanup result: state1 and state2 should be expired, state3 should remain
        mock_result = Mock()
        mock_result.rowcount = 2  # Two states cleaned up
        mock_session.exec.return_value = mock_result
        
        cleaned_count = oauth_repo.cleanup_expired_states()
        
        assert cleaned_count == 2
        
        # Verify operations: 3 creates + 1 cleanup = 4 commits, 1 cleanup query
        assert mock_session.add.call_count == 3
        assert mock_session.commit.call_count == 4  # 3 creates + 1 cleanup
    
    def test_concurrent_state_operations(self, oauth_repo, mock_session):
        """Test handling of concurrent OAuth state operations."""
        # Simulate concurrent operations by calling multiple methods
        
        # Mock different return values for different operations
        def mock_exec_side_effect(query):
            # Simulate different queries returning different results
            mock_result = Mock()
            if "SELECT" in str(query):
                # GET operation
                mock_result.scalar_one_or_none.return_value = OAuthState(
                    state="concurrent_state",
                    created_at=1609459200_000_000,
                    expires_at=1609459800_000_000
                )
            else:
                # DELETE operation
                mock_result.rowcount = 1
            return mock_result
        
        mock_session.exec.side_effect = mock_exec_side_effect
        
        # Perform concurrent-like operations
        oauth_repo.create_state("concurrent_state", 1609459800_000_000)
        retrieved_state = oauth_repo.get_state("concurrent_state")
        oauth_repo.delete_state("concurrent_state")
        
        # Verify all operations completed
        assert retrieved_state.state == "concurrent_state"
        assert mock_session.add.call_count == 1
        assert mock_session.commit.call_count == 2
        assert mock_session.exec.call_count == 2
    
    def test_repository_state_validation_edge_cases(self, oauth_repo, mock_session):
        """Test edge cases in OAuth state validation."""
        test_cases = [
            # (state, expires_at, description)
            ("", 1609459800_000_000, "empty state"),
            ("a", 1609459800_000_000, "single character state"),
            ("state with spaces", 1609459800_000_000, "state with spaces"),
            ("state-with-dashes", 1609459800_000_000, "state with dashes"),
            ("state_with_underscores", 1609459800_000_000, "state with underscores"),
            ("state.with.dots", 1609459800_000_000, "state with dots"),
            ("12345", 1609459800_000_000, "numeric state"),
            ("state", 0, "zero expiration time"),
            ("state", 999999999999999_999_999, "very large expiration time"),
        ]
        
        for state, expires_at, description in test_cases:
            # Should not raise exception for any of these cases
            created_state = oauth_repo.create_state(state, expires_at)
            assert created_state.state == state
            assert created_state.expires_at == expires_at
            
            # Test retrieval
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = created_state
            mock_session.exec.return_value = mock_result
            
            retrieved_state = oauth_repo.get_state(state)
            assert retrieved_state.state == state
            
            # Test deletion
            oauth_repo.delete_state(state)
        
        # Verify all operations completed without errors
        assert mock_session.add.call_count == len(test_cases)
        assert mock_session.commit.call_count == len(test_cases) * 2  # create + delete for each
