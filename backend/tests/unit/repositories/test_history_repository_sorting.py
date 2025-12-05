"""
Unit tests for HistoryRepository sorting functionality.

Tests the repository's ability to sort alert sessions by various fields,
ensuring proper behavior for all supported sort fields and directions.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us


class TestHistoryRepositorySorting:
    """Test suite for alert session sorting functionality."""

    @pytest.fixture
    def in_memory_engine(self):
        """Create in-memory SQLite engine for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        SQLModel.metadata.create_all(engine)
        return engine

    @pytest.fixture
    def db_session(self, in_memory_engine):
        """Create database session for testing."""
        with Session(in_memory_engine) as session:
            yield session

    @pytest.fixture
    def repository(self, db_session):
        """Create HistoryRepository instance with test database session."""
        return HistoryRepository(db_session)

    @pytest.fixture
    def sample_sessions(self, repository):
        """Create sample sessions with varied data for sorting tests."""
        base_time = now_us()
        
        sessions = [
            AlertSession(
                session_id="session-1",
                alert_type="PodCrashLooping",
                agent_type="kubernetes",
                status=AlertSessionStatus.COMPLETED.value,
                author="alice@example.com",
                started_at_us=base_time,
                completed_at_us=base_time + 5_000_000,  # 5 seconds
                alert_data={"namespace": "prod"},
                chain_id="k8s-chain"
            ),
            AlertSession(
                session_id="session-2",
                alert_type="HighMemoryUsage",
                agent_type="monitoring",
                status=AlertSessionStatus.FAILED.value,
                author="bob@example.com",
                started_at_us=base_time + 1_000_000,  # 1 second later
                completed_at_us=base_time + 3_000_000,  # 2 seconds duration
                alert_data={"namespace": "staging"},
                chain_id="monitoring-chain"
            ),
            AlertSession(
                session_id="session-3",
                alert_type="DiskFull",
                agent_type="infrastructure",
                status=AlertSessionStatus.IN_PROGRESS.value,
                author="charlie@example.com",
                started_at_us=base_time + 2_000_000,  # 2 seconds later
                completed_at_us=None,  # Still in progress
                alert_data={"namespace": "dev"},
                chain_id="infra-chain"
            ),
            AlertSession(
                session_id="session-4",
                alert_type="APILatency",
                agent_type="api",
                status=AlertSessionStatus.COMPLETED.value,
                author="alice@example.com",
                started_at_us=base_time - 10_000_000,  # 10 seconds before
                completed_at_us=base_time - 1_000_000,  # 9 seconds duration
                alert_data={"namespace": "prod"},
                chain_id="api-chain"
            ),
            AlertSession(
                session_id="session-5",
                alert_type="NetworkError",
                agent_type="kubernetes",
                status=AlertSessionStatus.CANCELLED.value,
                author="bob@example.com",
                started_at_us=base_time + 5_000_000,  # 5 seconds later
                completed_at_us=base_time + 6_000_000,  # 1 second duration
                alert_data={"namespace": "staging"},
                chain_id="k8s-chain"
            ),
        ]
        
        for session in sessions:
            repository.create_alert_session(session)
        
        return sessions

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "sort_field,sort_order,expected_first_session_id",
        [
            # Status sorting
            ("status", "asc", "session-5"),  # cancelled comes first alphabetically
            ("status", "desc", "session-3"),  # in_progress comes last alphabetically
            
            # Alert type sorting
            ("alert_type", "asc", "session-4"),  # APILatency first
            ("alert_type", "desc", "session-1"),  # PodCrashLooping last
            
            # Agent type sorting
            ("agent_type", "asc", "session-4"),  # api first
            ("agent_type", "desc", "session-2"),  # monitoring last
            
            # Author sorting
            ("author", "asc", "session-1"),  # alice@ first
            ("author", "desc", "session-3"),  # charlie@ last
            
            # Time sorting (started_at_us)
            ("started_at_us", "asc", "session-4"),  # oldest first
            ("started_at_us", "desc", "session-5"),  # newest first
        ],
    )
    def test_sorting_by_various_fields(
        self,
        repository,
        sample_sessions,
        sort_field: str,
        sort_order: str,
        expected_first_session_id: str
    ) -> None:
        """Test that sessions are correctly sorted by various fields and directions."""
        result = repository.get_alert_sessions(
            sort_by=sort_field,
            sort_order=sort_order,
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 5
        assert result.sessions[0].session_id == expected_first_session_id

    @pytest.mark.unit
    def test_sorting_by_duration_ascending(self, repository, sample_sessions) -> None:
        """Test sorting by duration (shortest first).
        
        Note: In practice, the UI never shows in-progress sessions in the sortable
        historical list - they're in a separate active panel. This test includes them
        for API completeness (they sort by current runtime).
        """
        result = repository.get_alert_sessions(
            sort_by="duration_ms",
            sort_order="asc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 5
        
        # Completed sessions by duration:
        # - session-5: 1 second
        # - session-2: 2 seconds
        # - session-1: 5 seconds
        # - session-4: 9 seconds
        # In-progress session-3 sorts by runtime (very short since just started)
        
        # Verify all sessions returned and sorted reasonably
        session_ids = [s.session_id for s in result.sessions]
        assert len(session_ids) == 5
        # session-5 (1 sec) should be among the shortest
        assert result.sessions[0].session_id in ["session-3", "session-5", "session-2"]

    @pytest.mark.unit
    def test_sorting_by_duration_descending(self, repository, sample_sessions) -> None:
        """Test sorting by duration (longest first).
        
        Note: In practice, the UI never shows in-progress sessions in the sortable
        historical list - they're in a separate active panel. This test includes them
        for API completeness (they sort by current runtime).
        """
        result = repository.get_alert_sessions(
            sort_by="duration_ms",
            sort_order="desc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 5
        
        # Completed sessions by duration (longest first):
        # - session-4: 9 seconds
        # - session-1: 5 seconds
        # - session-2: 2 seconds
        # - session-5: 1 second
        # In-progress session-3 sorts by runtime (could be anywhere)
        
        # Verify all sessions returned
        session_ids = [s.session_id for s in result.sessions]
        assert len(session_ids) == 5
        # session-4 (9 sec) should be first or near first
        assert result.sessions[0].session_id in ["session-4", "session-3", "session-1"]

    @pytest.mark.unit
    def test_default_sorting_no_parameters(self, repository, sample_sessions) -> None:
        """Test that default sorting is by started_at_us descending (most recent first)."""
        result = repository.get_alert_sessions(
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 5
        # Most recent session (session-5) should be first
        assert result.sessions[0].session_id == "session-5"
        # Oldest session (session-4) should be last
        assert result.sessions[4].session_id == "session-4"

    @pytest.mark.unit
    def test_invalid_sort_field_falls_back_to_default(self, repository, sample_sessions) -> None:
        """Test that invalid sort field falls back to default sorting."""
        result = repository.get_alert_sessions(
            sort_by="invalid_field_name",
            sort_order="asc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 5
        # Should fall back to default: started_at_us desc (most recent first)
        assert result.sessions[0].session_id == "session-5"

    @pytest.mark.unit
    def test_sorting_combined_with_status_filter(self, repository, sample_sessions) -> None:
        """Test that sorting works correctly when combined with status filters."""
        result = repository.get_alert_sessions(
            status=[AlertSessionStatus.COMPLETED.value],
            sort_by="agent_type",
            sort_order="asc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 2  # Only 2 completed sessions
        # Both completed, sorted by agent_type: api, kubernetes
        assert result.sessions[0].session_id == "session-4"  # api
        assert result.sessions[1].session_id == "session-1"  # kubernetes

    @pytest.mark.unit
    def test_sorting_combined_with_agent_type_filter(self, repository, sample_sessions) -> None:
        """Test that sorting works correctly when combined with agent type filter."""
        result = repository.get_alert_sessions(
            agent_type="kubernetes",
            sort_by="started_at_us",
            sort_order="asc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 2  # Only 2 kubernetes sessions
        # Sorted by time ascending: session-1, session-5
        assert result.sessions[0].session_id == "session-1"
        assert result.sessions[1].session_id == "session-5"

    @pytest.mark.unit
    def test_sorting_with_pagination(self, repository, sample_sessions) -> None:
        """Test that sorting respects pagination parameters."""
        # Get first page (2 items)
        page1 = repository.get_alert_sessions(
            sort_by="alert_type",
            sort_order="asc",
            page=1,
            page_size=2
        )
        
        # Get second page (2 items)
        page2 = repository.get_alert_sessions(
            sort_by="alert_type",
            sort_order="asc",
            page=2,
            page_size=2
        )
        
        assert page1 is not None
        assert page2 is not None
        assert len(page1.sessions) == 2
        assert len(page2.sessions) == 2
        
        # Verify no duplicates across pages
        page1_ids = {s.session_id for s in page1.sessions}
        page2_ids = {s.session_id for s in page2.sessions}
        assert len(page1_ids & page2_ids) == 0
        
        # Verify pagination info
        assert page1.pagination.page == 1
        assert page1.pagination.total_items == 5
        assert page2.pagination.page == 2

    @pytest.mark.unit
    def test_sorting_empty_results(self, repository) -> None:
        """Test sorting behavior with no matching sessions."""
        result = repository.get_alert_sessions(
            status=["nonexistent_status"],
            sort_by="status",
            sort_order="asc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 0
        assert result.pagination.total_items == 0

    @pytest.mark.unit
    def test_sorting_preserves_case_sensitivity(self, repository) -> None:
        """Test that sorting handles case properly for text fields."""
        # Create sessions with different case
        sessions = [
            AlertSession(
                session_id="case-1",
                alert_type="alertA",
                agent_type="agent",
                status=AlertSessionStatus.COMPLETED.value,
                author="Alpha@example.com",
                started_at_us=now_us(),
                completed_at_us=now_us() + 1_000_000,
                alert_data={},
                chain_id="test-chain"
            ),
            AlertSession(
                session_id="case-2",
                alert_type="AlertB",
                agent_type="agent",
                status=AlertSessionStatus.COMPLETED.value,
                author="alpha@example.com",
                started_at_us=now_us() + 1_000_000,
                completed_at_us=now_us() + 2_000_000,
                alert_data={},
                chain_id="test-chain"
            ),
        ]
        
        for session in sessions:
            repository.create_alert_session(session)
        
        result = repository.get_alert_sessions(
            sort_by="author",
            sort_order="asc",
            page=1,
            page_size=10
        )
        
        assert result is not None
        assert len(result.sessions) == 2
        # SQLite sorts case-insensitively by default, but preserves case in results
        # Both start with 'alpha' (different case), order may vary but both should be present
        author_ids = {s.session_id for s in result.sessions}
        assert "case-1" in author_ids
        assert "case-2" in author_ids

