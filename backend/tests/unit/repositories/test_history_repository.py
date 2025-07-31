"""
Unit tests for HistoryRepository.

Tests the repository layer functionality with in-memory database to ensure
proper data access layer implementation and database operations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlmodel import Session, SQLModel, create_engine

from tarsy.models.history import AlertSession, LLMInteraction, MCPCommunication
from tarsy.repositories.history_repository import HistoryRepository


class TestHistoryRepository:
    """Test suite for HistoryRepository class."""
    
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
    def sample_alert_session(self):
        """Create sample AlertSession for testing."""
        from tarsy.models.history import now_us
        return AlertSession(
            session_id="test-session-123",
            alert_id="alert-456",
            alert_data={
                "alert_type": "NamespaceTerminating",
                "environment": "production",
                "cluster": "k8s-prod",
                "namespace": "stuck-namespace"
            },
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="in_progress",
            started_at_us=now_us(),
            session_metadata={"test": "metadata"}
        )
    
    @pytest.fixture
    def sample_llm_interaction(self):
        """Create sample LLMInteraction for testing."""
        return LLMInteraction(
            interaction_id="llm-interaction-789",
            session_id="test-session-123",
            prompt_text="Analyze the namespace termination issue",
            response_text="The namespace is stuck due to finalizers",
            model_used="gpt-4",
            timestamp=datetime.now(timezone.utc),
            step_description="Initial analysis",
            duration_ms=1500
        )
    
    @pytest.fixture
    def sample_mcp_communication(self):
        """Create sample MCPCommunication for testing."""
        return MCPCommunication(
            communication_id="mcp-comm-101",
            session_id="test-session-123",
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get_namespace",
            tool_arguments={"namespace": "stuck-namespace"},
            tool_result={"status": "Terminating", "finalizers": ["test-finalizer"]},
            timestamp=datetime.now(timezone.utc),
            step_description="Check namespace status",
            duration_ms=800,
            success=True
        )
    
    @pytest.mark.unit
    def test_create_alert_session_success(self, repository, sample_alert_session):
        """Test successful alert session creation."""
        created_session = repository.create_alert_session(sample_alert_session)
        
        assert created_session.session_id == sample_alert_session.session_id
        
        # Verify session was saved to database
        retrieved_session = repository.get_alert_session(created_session.session_id)
        assert retrieved_session is not None
        assert retrieved_session.alert_id == sample_alert_session.alert_id
        assert retrieved_session.agent_type == sample_alert_session.agent_type
        assert retrieved_session.status == sample_alert_session.status
    
    @pytest.mark.unit
    def test_get_alert_session_not_found(self, repository):
        """Test getting alert session that doesn't exist."""
        session = repository.get_alert_session("non-existent-session")
        assert session is None
    
    @pytest.mark.unit
    def test_update_alert_session_success(self, repository, sample_alert_session):
        """Test successful alert session update."""
        # Create session first
        repository.create_alert_session(sample_alert_session)
        
        # Update session
        sample_alert_session.status = "completed"
        sample_alert_session.completed_at_us = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        
        result = repository.update_alert_session(sample_alert_session)
        assert result == True
        
        # Verify update
        updated_session = repository.get_alert_session(sample_alert_session.session_id)
        assert updated_session.status == "completed"
        assert updated_session.completed_at_us is not None
    
    @pytest.mark.unit
    def test_create_llm_interaction_success(self, repository, sample_alert_session, sample_llm_interaction):
        """Test successful LLM interaction creation."""
        # Create session first
        repository.create_alert_session(sample_alert_session)
        
        # Create interaction
        created_interaction = repository.create_llm_interaction(sample_llm_interaction)
        
        assert created_interaction.interaction_id == sample_llm_interaction.interaction_id
        
        # Verify interaction was saved
        interactions = repository.get_llm_interactions_for_session(sample_alert_session.session_id)
        assert len(interactions) == 1
        assert interactions[0].prompt_text == sample_llm_interaction.prompt_text
        assert interactions[0].response_text == sample_llm_interaction.response_text
    
    @pytest.mark.unit
    def test_create_mcp_communication_success(self, repository, sample_alert_session, sample_mcp_communication):
        """Test successful MCP communication creation."""
        # Create session first
        repository.create_alert_session(sample_alert_session)
        
        # Create communication
        created_communication = repository.create_mcp_communication(sample_mcp_communication)
        
        assert created_communication.communication_id == sample_mcp_communication.communication_id
        
        # Verify communication was saved
        communications = repository.get_mcp_communications_for_session(sample_alert_session.session_id)
        assert len(communications) == 1
        assert communications[0].server_name == sample_mcp_communication.server_name
        assert communications[0].tool_name == sample_mcp_communication.tool_name
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_filters(self, repository, sample_alert_session):
        """Test getting alert sessions with various filters."""
        # Create multiple sessions with different attributes
        session1 = sample_alert_session
        repository.create_alert_session(session1)
        
        session2 = AlertSession(
            session_id="test-session-456",
            alert_id="alert-789",
            alert_data={"alert_type": "HighCPU"},
            agent_type="KubernetesAgent",
            alert_type="HighCPU",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )
        repository.create_alert_session(session2)
        
        # Test status filter
        result = repository.get_alert_sessions(status="completed")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session2.session_id
        
        # Test agent_type filter
        result = repository.get_alert_sessions(agent_type="KubernetesAgent")
        assert len(result["sessions"]) == 2
        
        # Test alert_type filter
        result = repository.get_alert_sessions(alert_type="NamespaceTerminating")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_date_filters(self, repository):
        """Test getting alert sessions with date range filters."""
        # Create sessions with different timestamps
        from tarsy.models.history import now_us
        now_us_time = now_us()
        five_days_ago_us = now_us_time - (5 * 24 * 60 * 60 * 1000000)  # 5 days in microseconds
        one_hour_ago_us = now_us_time - (60 * 60 * 1000000)  # 1 hour in microseconds
        
        old_session = AlertSession(
            session_id="old-session",
            alert_id="old-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at_us=five_days_ago_us,
            completed_at_us=five_days_ago_us
        )
        
        new_session = AlertSession(
            session_id="new-session",
            alert_id="new-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at_us=one_hour_ago_us,
            completed_at_us=one_hour_ago_us
        )
        
        repository.create_alert_session(old_session)
        repository.create_alert_session(new_session)
        
        # Test start_date filter (convert unix timestamp back to datetime for current API)
        two_days_ago_us = now_us_time - (2 * 24 * 60 * 60 * 1000000)  # 2 days in microseconds
        result = repository.get_alert_sessions(start_date_us=two_days_ago_us)
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == new_session.session_id
        
        # Test end_date_us filter
        result = repository.get_alert_sessions(end_date_us=two_days_ago_us)
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == old_session.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_pagination(self, repository):
        """Test getting alert sessions with pagination."""
        # Create multiple sessions
        for i in range(5):
            session = AlertSession(
                session_id=f"session-{i}",
                alert_id=f"alert-{i}",
                alert_data={},
                agent_type="TestAgent",
                alert_type="test",
                status="completed",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=i)
            )
            repository.create_alert_session(session)
        
        # Test first page
        result = repository.get_alert_sessions(page=1, page_size=2)
        assert len(result["sessions"]) == 2
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["page_size"] == 2
        assert result["pagination"]["total_items"] == 5
        assert result["pagination"]["total_pages"] == 3
        
        # Test second page
        result = repository.get_alert_sessions(page=2, page_size=2)
        assert len(result["sessions"]) == 2
        assert result["pagination"]["page"] == 2
        
        # Test last page
        result = repository.get_alert_sessions(page=3, page_size=2)
        assert len(result["sessions"]) == 1
        assert result["pagination"]["page"] == 3
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_error_message(self, repository):
        """Test search functionality in error_message field."""
        from tarsy.models.history import now_us
        
        # Create sessions with different error messages
        session1 = AlertSession(
            session_id="test-session-search-1",
            alert_id="alert-search-1",
            alert_data={"alert_type": "NetworkError"},
            agent_type="NetworkAgent",
            alert_type="NetworkError",
            status="failed",
            started_at_us=now_us(),
            error_message="Connection refused by kubernetes API server"
        )
        repository.create_alert_session(session1)
        
        session2 = AlertSession(
            session_id="test-session-search-2", 
            alert_id="alert-search-2",
            alert_data={"alert_type": "DatabaseError"},
            agent_type="DatabaseAgent",
            alert_type="DatabaseError",
            status="failed",
            started_at_us=now_us(),
            error_message="Timeout occurred while querying database"
        )
        repository.create_alert_session(session2)
        
        # Test search in error messages
        result = repository.get_alert_sessions(search="kubernetes")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="timeout")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session2.session_id
        
        result = repository.get_alert_sessions(search="connection")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_final_analysis(self, repository):
        """Test search functionality in final_analysis field."""
        from tarsy.models.history import now_us
        
        # Create sessions with different analyses
        session1 = AlertSession(
            session_id="test-session-analysis-1",
            alert_id="alert-analysis-1", 
            alert_data={"alert_type": "NamespaceTerminating"},
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="completed",
            started_at_us=now_us(),
            final_analysis="The namespace is stuck because of finalizer blocking deletion. Use kubectl patch to remove finalizer."
        )
        repository.create_alert_session(session1)
        
        session2 = AlertSession(
            session_id="test-session-analysis-2",
            alert_id="alert-analysis-2",
            alert_data={"alert_type": "PodCrashLoop"},
            agent_type="KubernetesAgent", 
            alert_type="PodCrashLoop",
            status="completed",
            started_at_us=now_us(),
            final_analysis="Pod is crashing due to memory limits. Increase resource requests and limits in deployment."
        )
        repository.create_alert_session(session2)
        
        # Test search in final analysis
        result = repository.get_alert_sessions(search="finalizer")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="memory")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session2.session_id
        
        result = repository.get_alert_sessions(search="kubectl")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_alert_data_fields(self, repository):
        """Test search functionality in JSON alert_data fields."""
        from tarsy.models.history import now_us
        
        # Create sessions with different alert data
        session1 = AlertSession(
            session_id="test-session-json-1",
            alert_id="alert-json-1",
            alert_data={
                "alert_type": "NamespaceTerminating",
                "message": "Namespace superman-dev is stuck in terminating state",
                "context": "This usually happens when resources have finalizers",
                "namespace": "superman-dev",
                "environment": "production",
                "severity": "critical",
                "cluster": "k8s-prod-cluster"
            },
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating", 
            status="completed",
            started_at_us=now_us()
        )
        repository.create_alert_session(session1)
        
        session2 = AlertSession(
            session_id="test-session-json-2",
            alert_id="alert-json-2",
            alert_data={
                "alert_type": "UnidledPods", 
                "message": "High CPU usage detected on worker nodes",
                "context": "Multiple pods showing high resource consumption",
                "pod": "high-cpu-pod-123",
                "environment": "staging",
                "severity": "medium",
                "cluster": "k8s-staging-cluster"
            },
            agent_type="KubernetesAgent",
            alert_type="UnidledPods",
            status="completed", 
            started_at_us=now_us()
        )
        repository.create_alert_session(session2)
        
        # Test search in different JSON fields
        result = repository.get_alert_sessions(search="superman")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="finalizers")  
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="cpu")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session2.session_id
        
        result = repository.get_alert_sessions(search="production")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="critical")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="staging")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session2.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_case_insensitive(self, repository):
        """Test that search is case-insensitive."""
        from tarsy.models.history import now_us
        
        session = AlertSession(
            session_id="test-session-case-1",
            alert_id="alert-case-1",
            alert_data={
                "message": "Kubernetes Namespace Problem",
                "environment": "Production"
            },
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="completed",
            started_at_us=now_us(),
            error_message="Connection failed to API Server"
        )
        repository.create_alert_session(session)
        
        # Test case insensitive search
        result = repository.get_alert_sessions(search="kubernetes")  # lowercase
        assert len(result["sessions"]) == 1
        
        result = repository.get_alert_sessions(search="KUBERNETES")  # uppercase
        assert len(result["sessions"]) == 1
        
        result = repository.get_alert_sessions(search="KuBeRnEtEs")  # mixed case
        assert len(result["sessions"]) == 1
        
        result = repository.get_alert_sessions(search="production")  # lowercase environment
        assert len(result["sessions"]) == 1
        
        result = repository.get_alert_sessions(search="api server")  # lowercase error message
        assert len(result["sessions"]) == 1
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_combined_with_filters(self, repository):
        """Test search functionality combined with other filters."""
        from tarsy.models.history import now_us
        
        session1 = AlertSession(
            session_id="test-session-combined-1",
            alert_id="alert-combined-1",
            alert_data={"message": "Kubernetes namespace issue"},
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="completed",
            started_at_us=now_us()
        )
        repository.create_alert_session(session1)
        
        session2 = AlertSession(
            session_id="test-session-combined-2", 
            alert_id="alert-combined-2",
            alert_data={"message": "Kubernetes pod issue"},
            agent_type="KubernetesAgent",
            alert_type="UnidledPods",
            status="failed",
            started_at_us=now_us()
        )
        repository.create_alert_session(session2)
        
        session3 = AlertSession(
            session_id="test-session-combined-3",
            alert_id="alert-combined-3", 
            alert_data={"message": "Database connection issue"},
            agent_type="DatabaseAgent",
            alert_type="ConnectionTimeout",
            status="completed",
            started_at_us=now_us()
        )
        repository.create_alert_session(session3)
        
        # Test search + status filter
        result = repository.get_alert_sessions(search="kubernetes", status="completed")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session1.session_id
        
        # Test search + agent_type filter
        result = repository.get_alert_sessions(search="issue", agent_type="KubernetesAgent")
        assert len(result["sessions"]) == 2
        session_ids = [s.session_id for s in result["sessions"]]
        assert session1.session_id in session_ids
        assert session2.session_id in session_ids
        
        # Test search + alert_type filter
        result = repository.get_alert_sessions(search="kubernetes", alert_type="UnidledPods")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0].session_id == session2.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_no_matches(self, repository):
        """Test search functionality when no matches are found."""
        from tarsy.models.history import now_us
        
        session = AlertSession(
            session_id="test-session-nomatch-1",
            alert_id="alert-nomatch-1",
            alert_data={"message": "Simple alert message"},
            agent_type="SimpleAgent",
            alert_type="SimpleAlert",
            status="completed",
            started_at_us=now_us()
        )
        repository.create_alert_session(session)
        
        # Test search that should return no results
        result = repository.get_alert_sessions(search="nonexistent")
        assert len(result["sessions"]) == 0
        assert result["pagination"]["total_items"] == 0
        
        result = repository.get_alert_sessions(search="kubernetes")  # Not in any field
        assert len(result["sessions"]) == 0
        assert result["pagination"]["total_items"] == 0
    
    @pytest.mark.unit
    def test_get_session_timeline_chronological_order(self, repository, sample_alert_session):
        """Test session timeline reconstruction with chronological ordering."""
        # Create session
        repository.create_alert_session(sample_alert_session)
        
        # Create interactions and communications with specific timestamps
        base_time = datetime.now(timezone.utc)
        
        llm1 = LLMInteraction(
            interaction_id="llm-1",
            session_id=sample_alert_session.session_id,
            prompt_text="First prompt",
            response_text="First response",
            model_used="gpt-4",
            timestamp=base_time,
            step_description="First LLM interaction"
        )
        
        mcp1 = MCPCommunication(
            communication_id="mcp-1",
            session_id=sample_alert_session.session_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get",
            timestamp=base_time + timedelta(seconds=1),
            step_description="First MCP call",
            success=True
        )
        
        llm2 = LLMInteraction(
            interaction_id="llm-2",
            session_id=sample_alert_session.session_id,
            prompt_text="Second prompt",
            response_text="Second response",
            model_used="gpt-4",
            timestamp=base_time + timedelta(seconds=2),
            step_description="Second LLM interaction"
        )
        
        repository.create_llm_interaction(llm1)
        repository.create_mcp_communication(mcp1)
        repository.create_llm_interaction(llm2)
        
        # Get timeline
        timeline = repository.get_session_timeline(sample_alert_session.session_id)
        
        assert timeline is not None
        assert "session" in timeline
        assert "chronological_timeline" in timeline
        assert "llm_interactions" in timeline
        assert "mcp_communications" in timeline
        
        # Verify chronological order
        events = timeline["chronological_timeline"]
        assert len(events) == 3
        assert events[0]["type"] == "llm"
        assert events[1]["type"] == "mcp"
        assert events[2]["type"] == "llm"
        
                # Verify timeline is ordered by timestamp_us
        for i in range(len(events) - 1):
            assert events[i]["timestamp_us"] <= events[i + 1]["timestamp_us"]

    @pytest.mark.unit
    def test_get_session_timeline_unix_timestamp_precision(self, repository, sample_alert_session):
        """Test session timeline with Unix timestamp precision and chronological ordering."""
        # Create session
        repository.create_alert_session(sample_alert_session)
        
        # Create interactions with specific Unix timestamps (microseconds since epoch)
        base_timestamp_us = 1705314645123456  # 2024-01-15T10:30:45.123456Z UTC
        
        # Create LLM interaction with precise timestamp
        llm_interaction = LLMInteraction(
            interaction_id="llm-precise",
            session_id=sample_alert_session.session_id,
            prompt_text="Precise timestamp prompt",
            response_text="Precise timestamp response",
            model_used="gpt-4",
            timestamp_us=base_timestamp_us,
            step_description="LLM interaction with precise timestamp"
        )
        
        # Create MCP communication 1 second later
        mcp_communication = MCPCommunication(
            communication_id="mcp-later",
            session_id=sample_alert_session.session_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get",
            timestamp_us=base_timestamp_us + 1_000_000,  # 1 second later
            step_description="MCP call 1 second later",
            success=True
        )
        
        # Create another LLM interaction 500ms after first
        llm_interaction_middle = LLMInteraction(
            interaction_id="llm-middle",
            session_id=sample_alert_session.session_id,
            prompt_text="Middle timestamp prompt",
            response_text="Middle timestamp response",
            model_used="gpt-4",
            timestamp_us=base_timestamp_us + 500_000,  # 500ms later
            step_description="LLM interaction in middle"
        )
        
        repository.create_llm_interaction(llm_interaction)
        repository.create_mcp_communication(mcp_communication)
        repository.create_llm_interaction(llm_interaction_middle)
        
        # Get timeline
        timeline = repository.get_session_timeline(sample_alert_session.session_id)
        
        assert timeline is not None
        events = timeline["chronological_timeline"]
        assert len(events) == 3
        
        # Verify chronological ordering by timestamp_us
        assert events[0]["id"] == "llm-precise"
        assert events[1]["id"] == "llm-middle"
        assert events[2]["id"] == "mcp-later"
        
        # Verify Unix timestamps are preserved for sorting
        assert events[0]["timestamp_us"] == base_timestamp_us
        assert events[1]["timestamp_us"] == base_timestamp_us + 500_000
        assert events[2]["timestamp_us"] == base_timestamp_us + 1_000_000
        
        # Verify Unix timestamps are returned as integers
        assert events[0]["timestamp_us"] == base_timestamp_us
        assert events[1]["timestamp_us"] == base_timestamp_us + 500_000  # +500ms
        assert events[2]["timestamp_us"] == base_timestamp_us + 1_000_000  # +1s
        
        # Verify all timestamp_us values are integers
        for event in events:
            assert isinstance(event["timestamp_us"], int)
            assert event["timestamp_us"] > 0
            
            # Verify no ISO string conversion is happening anymore
            assert "timestamp" not in event or event.get("timestamp") is None

    @pytest.mark.unit
    def test_get_active_sessions(self, repository):
        """Test getting active sessions."""
        # Create active and completed sessions
        active_session = AlertSession(
            session_id="active-session",
            alert_id="active-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="in_progress",
            started_at=datetime.now(timezone.utc)
        )
        
        completed_session = AlertSession(
            session_id="completed-session",
            alert_id="completed-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )
        
        repository.create_alert_session(active_session)
        repository.create_alert_session(completed_session)
        
        # Get active sessions
        active_sessions = repository.get_active_sessions()
        
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == active_session.session_id
        assert active_sessions[0].status == "in_progress"
    
    @pytest.mark.unit
    def test_cleanup_old_sessions(self, repository):
        """Test cleanup of old sessions."""
        # Create old and new sessions
        from tarsy.models.history import now_us
        now_us_time = now_us()
        hundred_days_ago_us = now_us_time - (100 * 24 * 60 * 60 * 1000000)  # 100 days in microseconds
        one_day_ago_us = now_us_time - (24 * 60 * 60 * 1000000)  # 1 day in microseconds
        
        old_session = AlertSession(
            session_id="old-session",
            alert_id="old-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at_us=hundred_days_ago_us,
            completed_at_us=hundred_days_ago_us
        )
        
        new_session = AlertSession(
            session_id="new-session",
            alert_id="new-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at_us=one_day_ago_us,
            completed_at_us=one_day_ago_us
        )
        
        repository.create_alert_session(old_session)
        repository.create_alert_session(new_session)
        
        # Cleanup sessions older than 90 days
        cleaned_count = repository.cleanup_old_sessions(retention_days=90)
        
        assert cleaned_count == 1
        
        # Verify old session was deleted and new session remains
        assert repository.get_alert_session("old-session") is None
        assert repository.get_alert_session("new-session") is not None
    
    @pytest.mark.unit
    def test_complex_filter_combinations(self, repository):
        """Test complex filter combinations with AND logic."""
        # Create sessions with various attributes
        now = datetime.now(timezone.utc)
        
        sessions_data = [
            ("session-1", "NamespaceTerminating", "KubernetesAgent", "completed", now - timedelta(hours=1)),
            ("session-2", "NamespaceTerminating", "KubernetesAgent", "in_progress", now - timedelta(hours=2)),
            ("session-3", "HighCPU", "KubernetesAgent", "completed", now - timedelta(hours=3)),
            ("session-4", "NamespaceTerminating", "GenericAgent", "completed", now - timedelta(hours=4)),
        ]
        
        for session_id, alert_type, agent_type, status, started_at in sessions_data:
            session = AlertSession(
                session_id=session_id,
                alert_id=f"alert-{session_id}",
                alert_data={"alert_type": alert_type},
                agent_type=agent_type,
                alert_type=alert_type,
                status=status,
                started_at=started_at,
                completed_at=started_at + timedelta(minutes=10) if status == "completed" else None
            )
            repository.create_alert_session(session)
        
        # Test alert_type + status combination
        result = repository.get_alert_sessions(
            alert_type="NamespaceTerminating",
            status="completed"
        )
        assert len(result["sessions"]) == 2  # session-1 and session-4
        
        # Test alert_type + status + agent_type combination
        result = repository.get_alert_sessions(
            alert_type="NamespaceTerminating",
            status="completed",
            agent_type="KubernetesAgent"
        )
        assert len(result["sessions"]) == 1  # only session-1
        assert result["sessions"][0].session_id == "session-1"
        
        # Test agent_type + status + time_range combination
        result = repository.get_alert_sessions(
            agent_type="KubernetesAgent",
            status="completed",
            start_date_us=int((now - timedelta(hours=3.5)).timestamp() * 1_000_000)  # Should get session-1 and session-3
        )
        assert len(result["sessions"]) == 2
        session_ids = [s.session_id for s in result["sessions"]]
        assert "session-1" in session_ids
        assert "session-3" in session_ids


class TestHistoryRepositoryErrorHandling:
    """Test suite for HistoryRepository error handling scenarios."""
    
    @pytest.fixture
    def sample_alert_session(self):
        """Create sample AlertSession for testing."""
        return AlertSession(
            session_id="test-session-123",
            alert_id="alert-456",
            alert_data={
                "alert_type": "NamespaceTerminating",
                "environment": "production",
                "cluster": "k8s-prod",
                "namespace": "stuck-namespace"
            },
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="in_progress",
            started_at=datetime.now(timezone.utc),
            session_metadata={"test": "metadata"}
        )
    
    @pytest.fixture
    def repository_with_session_error(self):
        """Create repository with session that will raise errors."""
        mock_session = Mock()
        mock_session.exec.side_effect = Exception("Database error")
        mock_session.add.side_effect = Exception("Database error")
        mock_session.commit.side_effect = Exception("Database error")
        
        return HistoryRepository(mock_session)
    
    @pytest.mark.unit
    def test_create_alert_session_database_error(self, repository_with_session_error, sample_alert_session):
        """Test alert session creation with database error."""
        result = repository_with_session_error.create_alert_session(sample_alert_session)
        assert result is None
    
    @pytest.mark.unit
    def test_get_alert_sessions_database_error(self, repository_with_session_error):
        """Test getting alert sessions with database error."""
        result = repository_with_session_error.get_alert_sessions()
        
        # Should return empty result structure
        assert result["sessions"] == []
        assert result["pagination"]["total_items"] == 0
    
    @pytest.mark.unit
    def test_get_session_timeline_database_error(self, repository_with_session_error):
        """Test getting session timeline with database error."""
        result = repository_with_session_error.get_session_timeline("test-session")
        assert result is None
    
    @pytest.mark.unit
    def test_cleanup_old_sessions_database_error(self, repository_with_session_error):
        """Test cleanup old sessions with database error."""
        result = repository_with_session_error.cleanup_old_sessions(90)
        assert result == 0


class TestHistoryRepositoryPerformance:
    """Test suite for HistoryRepository performance scenarios."""
    
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
    def repository_with_large_dataset(self, repository):
        """Create repository with large dataset for performance testing."""
        # Create 100 sessions with interactions and communications
        now = datetime.now(timezone.utc)
        
        for i in range(100):
            session = AlertSession(
                session_id=f"perf-session-{i}",
                alert_id=f"perf-alert-{i}",
                alert_data={"alert_type": f"TestAlert{i % 5}"},
                agent_type="TestAgent",
                alert_type=f"TestAlert{i % 5}",
                status="completed" if i % 2 == 0 else "in_progress",
                started_at=now - timedelta(minutes=i),
                completed_at=now - timedelta(minutes=i-5) if i % 2 == 0 else None
            )
            repository.create_alert_session(session)
            
            # Add some interactions for every 10th session
            if i % 10 == 0:
                interaction = LLMInteraction(
                    interaction_id=f"perf-interaction-{i}",
                    session_id=session.session_id,
                    prompt_text=f"Prompt {i}",
                    response_text=f"Response {i}",
                    model_used="gpt-4",
                    timestamp=now - timedelta(minutes=i-1),
                    step_description=f"Interaction {i}"
                )
                repository.create_llm_interaction(interaction)
        
        return repository
    
    @pytest.mark.unit
    def test_pagination_performance_large_dataset(self, repository_with_large_dataset):
        """Test pagination performance with large dataset."""
        # Test that pagination works efficiently with large dataset
        result = repository_with_large_dataset.get_alert_sessions(page=1, page_size=10)
        
        assert len(result["sessions"]) == 10
        assert result["pagination"]["total_items"] == 100
        assert result["pagination"]["total_pages"] == 10
        
        # Test middle page
        result = repository_with_large_dataset.get_alert_sessions(page=5, page_size=10)
        assert len(result["sessions"]) == 10
        assert result["pagination"]["page"] == 5
    
    @pytest.mark.unit
    def test_filtering_performance_large_dataset(self, repository_with_large_dataset):
        """Test filtering performance with large dataset."""
        # Test status filter performance
        result = repository_with_large_dataset.get_alert_sessions(status="completed", page_size=100)
        assert len(result["sessions"]) == 50  # Half of the sessions
        
        # Test combined filters performance
        result = repository_with_large_dataset.get_alert_sessions(
            status="completed",
            alert_type="TestAlert0"
        )
        # Should get completed sessions with TestAlert0 (sessions 0, 10, 20, etc.)
        assert len(result["sessions"]) == 10

    # Dashboard-specific tests
    @pytest.mark.unit
    def test_get_dashboard_metrics_success(self, db_session):
        """Test successful dashboard metrics calculation."""
        repo = HistoryRepository(db_session)
        
        # Create test sessions with different statuses
        from datetime import datetime, timedelta, timezone
        
        # Active sessions
        for i in range(3):
            session = AlertSession(
                session_id=f"active_{i}",
                alert_id=f"alert_active_{i}",
                agent_type="kubernetes",
                alert_type="PodCrashLooping",
                status="in_progress",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
                alert_data={"test": "data"}
            )
            db_session.add(session)
        
        # Completed sessions
        for i in range(5):
            session = AlertSession(
                session_id=f"completed_{i}",
                alert_id=f"alert_completed_{i}",
                agent_type="network" if i % 2 else "kubernetes",
                alert_type="ServiceDown" if i % 2 else "PodCrashLooping",
                status="completed",
                started_at=datetime.now(timezone.utc) - timedelta(hours=2),
                completed_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=30),
                alert_data={"test": "data"}
            )
            db_session.add(session)
        
        # Failed sessions
        for i in range(2):
            session = AlertSession(
                session_id=f"failed_{i}",
                alert_id=f"alert_failed_{i}",
                agent_type="database",
                alert_type="ConnectionTimeout",
                status="failed",
                started_at=datetime.now(timezone.utc) - timedelta(hours=1),
                completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
                error_message="Connection timeout",
                alert_data={"test": "data"}
            )
            db_session.add(session)
        
        # Add some interactions for counting
        for i in range(10):
            interaction = LLMInteraction(
                interaction_id=f"llm_{i}",
                session_id=f"completed_{i % 5}",
                prompt_text="Test prompt",
                response_text="Test response",
                model_used="test-model",
                step_description="Test step",
                timestamp=datetime.now(timezone.utc)
            )
            db_session.add(interaction)
        
        for i in range(8):
            communication = MCPCommunication(
                communication_id=f"mcp_{i}",
                session_id=f"completed_{i % 5}",
                server_name="test-server",
                communication_type="tool_call",
                tool_name="test-tool",
                success=True,
                step_description="Test step",
                timestamp=datetime.now(timezone.utc)
            )
            db_session.add(communication)
        
        db_session.commit()
        
        result = repo.get_dashboard_metrics()
        
        # Verify session counts
        assert result["active_sessions"] == 3  # 3 in_progress sessions
        assert result["completed_sessions"] == 5  # 5 completed sessions
        assert result["failed_sessions"] == 2  # 2 failed sessions
        
        # Verify interaction counts
        assert result["total_interactions"] == 18  # 10 LLM + 8 MCP
        
        # Verify metrics are calculated
        assert "avg_session_duration" in result
        assert "error_rate" in result
        assert "last_24h_sessions" in result
        
        # Verify error rate calculation (2 failed out of 10 total = 20%)
        assert result["error_rate"] == 20.0
    
    @pytest.mark.unit
    def test_get_dashboard_metrics_empty_database(self, db_session):
        """Test dashboard metrics with empty database."""
        repo = HistoryRepository(db_session)
        
        result = repo.get_dashboard_metrics()
        
        # All counts should be zero
        assert result["active_sessions"] == 0
        assert result["completed_sessions"] == 0
        assert result["failed_sessions"] == 0
        assert result["total_interactions"] == 0
        assert result["avg_session_duration"] == 0.0
        assert result["error_rate"] == 0.0
        assert result["last_24h_sessions"] == 0
    
    @pytest.mark.unit
    def test_get_filter_options_success(self, db_session):
        """Test successful filter options retrieval."""
        repo = HistoryRepository(db_session)
        
        # Create test data with different types
        sessions = [
            AlertSession(session_id="1", alert_id="a1", agent_type="kubernetes", alert_type="PodCrashLooping", status="in_progress", alert_data={}),
            AlertSession(session_id="2", alert_id="a2", agent_type="network", alert_type="ServiceDown", status="completed", alert_data={}),
            AlertSession(session_id="3", alert_id="a3", agent_type="database", alert_type="ConnectionTimeout", status="failed", alert_data={})
        ]
        
        for session in sessions:
            db_session.add(session)
        db_session.commit()
        
        result = repo.get_filter_options()
        
        # Verify agent types (should include kubernetes, network, database)
        assert "agent_types" in result
        assert len(result["agent_types"]) == 3
        assert "kubernetes" in result["agent_types"]
        assert "network" in result["agent_types"]
        assert "database" in result["agent_types"]
        
        # Verify alert types
        assert "alert_types" in result
        assert len(result["alert_types"]) == 3
        assert "PodCrashLooping" in result["alert_types"]
        assert "ServiceDown" in result["alert_types"]
        assert "ConnectionTimeout" in result["alert_types"]
        
        # Verify status options
        assert "status_options" in result
        assert len(result["status_options"]) == 4
        assert "pending" in result["status_options"]
        assert "in_progress" in result["status_options"]
        assert "completed" in result["status_options"]
        assert "failed" in result["status_options"]
        
        # Verify time ranges
        assert "time_ranges" in result
        assert len(result["time_ranges"]) == 5
    
    @pytest.mark.unit
    def test_get_filter_options_empty_database(self, db_session):
        """Test filter options with empty database."""
        repo = HistoryRepository(db_session)
        
        result = repo.get_filter_options()
        
        # Should return empty lists for dynamic options
        assert result["agent_types"] == []
        assert result["alert_types"] == []
        # Status options should always return all possible statuses (not dynamic from database)
        assert len(result["status_options"]) == 4
        assert result["status_options"] == ["pending", "in_progress", "completed", "failed"]
        
        # Time ranges should still be present (static)
        assert len(result["time_ranges"]) == 5
    
    @pytest.mark.unit
    def test_get_filter_options_sorted_results(self, db_session):
        """Test that filter options are properly sorted."""
        repo = HistoryRepository(db_session)
        
        # Create test data in non-alphabetical order
        sessions = [
            AlertSession(session_id="1", alert_id="a1", agent_type="zebra", alert_type="ZAlert", status="pending", alert_data={}),
            AlertSession(session_id="2", alert_id="a2", agent_type="alpha", alert_type="AAlert", status="completed", alert_data={}),
            AlertSession(session_id="3", alert_id="a3", agent_type="beta", alert_type="BAlert", status="in_progress", alert_data={})
        ]
        
        for session in sessions:
            db_session.add(session)
        db_session.commit()
        
        result = repo.get_filter_options()
        
        # Verify sorting
        assert result["agent_types"] == sorted(result["agent_types"])
        assert result["alert_types"] == sorted(result["alert_types"])
        # Status options are returned in constant definition order (not sorted)
        assert result["status_options"] == ["pending", "in_progress", "completed", "failed"]
    
    @pytest.mark.unit
    def test_dashboard_metrics_duration_calculation(self, db_session):
        """Test average duration calculation in dashboard metrics."""
        repo = HistoryRepository(db_session)
        
        # Create sessions with known durations
        
        # Session 1: 60 seconds duration
        from tarsy.models.history import now_us
        now_us_time = now_us()
        one_minute_ago_us = now_us_time - (60 * 1000000)  # 1 minute in microseconds
        two_minutes_ago_us = now_us_time - (2 * 60 * 1000000)  # 2 minutes in microseconds
        four_minutes_ago_us = now_us_time - (4 * 60 * 1000000)  # 4 minutes in microseconds
        
        session1 = AlertSession(
            session_id="duration_test_1",
            alert_id="alert_1",
            agent_type="test",
            status="completed",
            started_at_us=two_minutes_ago_us,
            completed_at_us=one_minute_ago_us,
            alert_data={}
        )
        
        # Session 2: 120 seconds duration
        session2 = AlertSession(
            session_id="duration_test_2",
            alert_id="alert_2",
            agent_type="test",
            status="completed",
            started_at_us=four_minutes_ago_us,
            completed_at_us=two_minutes_ago_us,
            alert_data={}
        )
        
        db_session.add(session1)
        db_session.add(session2)
        db_session.commit()
        
        result = repo.get_dashboard_metrics()
        
        # Average should be (60 + 120) / 2 = 90 seconds
        assert result["avg_session_duration"] == 90.0
    
    @pytest.mark.unit
    def test_export_session_data_success(self, db_session):
        """Test successful session data export."""
        repo = HistoryRepository(db_session)
        
        # Create test session with all required fields
        session = AlertSession(
            session_id="test_export_session",
            alert_id="test_alert_export",
            agent_type="KubernetesAgent",
            alert_type="TestAlert",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            alert_data={"environment": "test", "cluster": "test-cluster"},
            session_metadata={"description": "Test export session"}
        )
        
        # Add LLM interaction with required fields
        llm_interaction = LLMInteraction(
            session_id="test_export_session",
            interaction_id="test_llm_1",
            model_used="test-model",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=4),
            prompt_text="Test prompt",
            response_text="Test response",
            step_description="Test LLM interaction"
        )
        
        # Add MCP communication with required fields
        mcp_communication = MCPCommunication(
            session_id="test_export_session",
            communication_id="test_mcp_1",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=4),
            server_name="test-server",
            communication_type="tool_call",
            tool_name="test-tool",
            tool_arguments={"action": "test"},
            tool_result={"result": "success"},
            success=True,
            step_description="Test MCP communication"
        )
        
        db_session.add(session)
        db_session.add(llm_interaction)
        db_session.add(mcp_communication)
        db_session.commit()
        
        # Test JSON export
        result = repo.export_session_data("test_export_session", "json")
        
        # Verify result structure
        assert result["session_id"] == "test_export_session"
        assert result["format"] == "json"
        assert result["error"] is None
        assert result["data"] is not None
        
        # Verify session data
        session_data = result["data"]["session"]
        assert session_data["session_id"] == "test_export_session"
        assert session_data["alert_id"] == "test_alert_export"
        assert session_data["agent_type"] == "KubernetesAgent"
        assert session_data["status"] == "completed"
        assert session_data["alert_data"]["environment"] == "test"
        
        # Verify timeline data
        timeline_data = result["data"]["timeline"]
        assert timeline_data["session"]["session_id"] == "test_export_session"
        assert timeline_data["session"]["total_interactions"] == 2  # 1 LLM + 1 MCP interaction
        
        # Verify export metadata
        export_metadata = result["data"]["export_metadata"]
        assert export_metadata["format"] == "json"
        assert export_metadata["total_interactions"] == 2  # Should match timeline interactions
        assert "exported_at" in export_metadata
        assert "session_duration_seconds" in export_metadata
    
    @pytest.mark.unit
    def test_export_session_data_not_found(self, db_session):
        """Test export with non-existent session."""
        repo = HistoryRepository(db_session)
        
        result = repo.export_session_data("nonexistent_session", "json")
        
        # Verify error response
        assert result["session_id"] == "nonexistent_session"
        assert result["format"] == "json"
        assert result["data"] is None
        assert "not found" in result["error"].lower()
    
    @pytest.mark.unit
    def test_export_session_data_csv_format(self, db_session):
        """Test export with CSV format parameter."""
        repo = HistoryRepository(db_session)
        
        # Create minimal test session
        session = AlertSession(
            session_id="test_csv_session",
            alert_id="test_alert_csv",
            agent_type="KubernetesAgent",
            alert_type="TestAlert",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            alert_data={}
        )
        
        db_session.add(session)
        db_session.commit()
        
        result = repo.export_session_data("test_csv_session", "csv")
        
        # Verify format is preserved in response
        assert result["format"] == "csv"
        assert result["session_id"] == "test_csv_session"
        assert result["data"] is not None
        assert result["data"]["export_metadata"]["format"] == "csv"
    
    @pytest.mark.unit
    def test_search_sessions_success(self, db_session):
        """Test successful session search."""
        repo = HistoryRepository(db_session)
        
        # Create test sessions with searchable content
        session1 = AlertSession(
            session_id="search_session_1",
            alert_id="namespace_terminating_alert",
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=8),
            alert_data={"namespace": "production-ns", "environment": "production"}
        )
        
        session2 = AlertSession(
            session_id="search_session_2",
            alert_id="pod_crash_alert",
            agent_type="KubernetesAgent",
            alert_type="PodCrashLoop",
            status="failed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            alert_data={"namespace": "staging-ns", "environment": "staging"},
            error_message="Failed to resolve namespace issue"
        )
        
        session3 = AlertSession(
            session_id="search_session_3",
            alert_id="unrelated_alert",
            agent_type="DatabaseAgent",
            alert_type="ConnectionTimeout",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            alert_data={"database": "main-db"}
        )
        
        db_session.add(session1)
        db_session.add(session2)
        db_session.add(session3)
        db_session.commit()
        
        # Test search by alert_type
        results = repo.search_sessions("namespace", 10)
        
        # Should find sessions 1 and 2 (both have "namespace" in content)
        assert len(results) == 2
        session_ids = [r["session_id"] for r in results]
        assert "search_session_1" in session_ids
        assert "search_session_2" in session_ids
        
        # Verify result structure
        result = results[0]
        assert "session_id" in result
        assert "alert_id" in result
        assert "agent_type" in result
        assert "alert_type" in result
        assert "status" in result
        assert "started_at_us" in result
        assert "completed_at_us" in result
        assert "duration_seconds" in result
        
        # Test search by agent_type
        k8s_results = repo.search_sessions("KubernetesAgent", 10)
        assert len(k8s_results) == 2  # sessions 1 and 2
        
        # Test search by error message
        error_results = repo.search_sessions("Failed to resolve", 10)
        assert len(error_results) == 1
        assert error_results[0]["session_id"] == "search_session_2"
    
    @pytest.mark.unit
    def test_search_sessions_json_field_search(self, db_session):
        """Test search within JSON fields."""
        repo = HistoryRepository(db_session)
        
        # Create session with JSON data
        session = AlertSession(
            session_id="json_search_session",
            alert_id="json_test_alert",
            agent_type="KubernetesAgent",
            alert_type="TestAlert",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            alert_data={"environment": "production", "cluster": "prod-cluster-01"},
            session_metadata={"description": "Production cluster maintenance"}
        )
        
        db_session.add(session)
        db_session.commit()
        
        # Test search by environment in alert_data
        env_results = repo.search_sessions("production", 10)
        assert len(env_results) == 1
        assert env_results[0]["session_id"] == "json_search_session"
        
        # Test search by cluster in alert_data
        cluster_results = repo.search_sessions("prod-cluster-01", 10)
        assert len(cluster_results) == 1
        assert cluster_results[0]["session_id"] == "json_search_session"
        
        # Test search by description in session_metadata
        desc_results = repo.search_sessions("maintenance", 10)
        assert len(desc_results) == 1
        assert desc_results[0]["session_id"] == "json_search_session"
    
    @pytest.mark.unit
    def test_search_sessions_empty_results(self, db_session):
        """Test search with no matching results."""
        repo = HistoryRepository(db_session)
        
        # Create a session that won't match our search
        session = AlertSession(
            session_id="no_match_session",
            alert_id="different_alert",
            agent_type="DatabaseAgent",
            alert_type="ConnectionTimeout",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            alert_data={"database": "test-db"}
        )
        
        db_session.add(session)
        db_session.commit()
        
        # Search for something that doesn't exist
        results = repo.search_sessions("nonexistent_term", 10)
        assert results == []
    
    @pytest.mark.unit
    def test_search_sessions_limit_parameter(self, db_session):
        """Test search with limit parameter."""
        repo = HistoryRepository(db_session)
        
        # Create multiple matching sessions
        for i in range(5):
            session = AlertSession(
                session_id=f"limit_test_session_{i}",
                alert_id=f"test_alert_{i}",
                agent_type="TestAgent",
                alert_type="TestAlert",
                status="completed",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=10-i),
                completed_at=datetime.now(timezone.utc) - timedelta(minutes=8-i),
                alert_data={}
            )
            db_session.add(session)
        
        db_session.commit()
        
        # Test with limit=2
        results = repo.search_sessions("TestAgent", 2)
        assert len(results) == 2
        
        # Test with limit=10 (should return all 5)
        results = repo.search_sessions("TestAgent", 10)
        assert len(results) == 5
    
    @pytest.mark.unit
    def test_search_sessions_ordering(self, db_session):
        """Test that search results are ordered by most recent first."""
        repo = HistoryRepository(db_session)
        
        # Create sessions with different timestamps
        older_session = AlertSession(
            session_id="older_session",
            alert_id="older_alert",
            agent_type="TestAgent",
            alert_type="TestAlert",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            completed_at=datetime.now(timezone.utc) - timedelta(hours=2) + timedelta(minutes=1),
            alert_data={}
        )
        
        newer_session = AlertSession(
            session_id="newer_session",
            alert_id="newer_alert",
            agent_type="TestAgent",
            alert_type="TestAlert",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=29),
            alert_data={}
        )
        
        db_session.add(older_session)
        db_session.add(newer_session)
        db_session.commit()
        
        results = repo.search_sessions("TestAgent", 10)
        
        # Newer session should come first
        assert len(results) == 2
        assert results[0]["session_id"] == "newer_session"
        assert results[1]["session_id"] == "older_session"

 
@pytest.mark.unit  
class TestHistoryRepositoryDuplicatePrevention:
    """Standalone test class for duplicate prevention (kept for backwards compatibility)."""
    
    def test_duplicate_prevention_documented(self):
        """Test that documents the duplicate prevention implementation."""
        # This test serves as documentation that duplicate prevention
        # is implemented in the create_alert_session method
        from tarsy.repositories.history_repository import HistoryRepository
        
        # Verify the method exists and has the expected behavior
        assert hasattr(HistoryRepository, 'create_alert_session')
        
        # Check that the implementation includes duplicate checking
        import inspect
        source = inspect.getsource(HistoryRepository.create_alert_session)
        assert 'existing_session' in source, "Should check for existing sessions"
        assert 'alert_id' in source, "Should check by alert_id"


class TestFlexibleAlertDataPerformance:
    """Pragmatic performance tests for flexible alert data JSON queries."""
    
    @pytest.fixture
    def in_memory_engine(self):
        """Create in-memory SQLite engine for performance testing."""
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
    def repository_with_flexible_data(self, repository):
        """Create repository with flexible alert data for performance testing."""
        from datetime import datetime, timezone
        
        # Create 100 sessions with various flexible data structures
        for i in range(100):
            # Create diverse alert data structures
            if i % 4 == 0:  # Monitoring alerts (25%)
                alert_data = {
                    "service": f"service-{i}",
                    "environment": "production" if i % 2 == 0 else "staging",
                    "severity": "critical" if i % 3 == 0 else "warning",
                    "cluster": f"cluster-{i % 5}",
                    "metrics": {
                        "cpu_usage": 50 + (i % 50),
                        "memory_usage": 30 + (i % 70),
                        "network": {"in_bytes": i * 1000, "out_bytes": i * 2000}
                    },
                    "labels": [f"label-{j}" for j in range(i % 5)],
                    "nested_config": {
                        "thresholds": {"cpu": 90, "memory": 80},
                        "intervals": [30, 60, 120]
                    }
                }
            elif i % 4 == 1:  # Database alerts (25%)
                alert_data = {
                    "database_type": "postgresql",
                    "environment": "production" if i % 3 == 0 else "staging", 
                    "severity": "high" if i % 2 == 0 else "medium",
                    "cluster": f"db-cluster-{i % 3}",
                    "connection_pool": {
                        "active": 50 + (i % 50),
                        "max": 100,
                        "waiting": i % 20
                    },
                    "queries": [
                        {"id": f"q{j}", "duration": (i + j) * 100} 
                        for j in range(i % 3 + 1)
                    ]
                }
            elif i % 4 == 2:  # Network alerts (25%)
                alert_data = {
                    "network_type": "switch",
                    "environment": "production",
                    "severity": "critical" if i % 5 == 0 else "warning",
                    "cluster": f"network-{i % 4}",
                    "interface_stats": {
                        "port1": {"in": i * 1000, "out": i * 2000, "errors": i % 10},
                        "port2": {"in": i * 800, "out": i * 1500, "errors": i % 5}
                    },
                    "bgp_neighbors": [f"neighbor-{j}" for j in range(i % 4)]
                }
            else:  # Kubernetes alerts (25%)
                alert_data = {
                    "namespace": f"ns-{i % 10}",
                    "environment": "production" if i % 2 == 0 else "development",
                    "severity": "critical" if i % 6 == 0 else "warning", 
                    "cluster": f"k8s-cluster-{i % 3}",
                    "pod_info": {
                        "name": f"pod-{i}",
                        "status": "Running" if i % 3 != 0 else "Pending",
                        "resources": {"cpu": f"{i % 4}00m", "memory": f"{(i % 8) * 128}Mi"}
                    },
                    "events": [
                        {"type": "Warning", "reason": f"reason-{j}", "count": j + 1}
                        for j in range(i % 3)
                    ]
                }
            
            session = AlertSession(
                session_id=f"perf_test_{i}",
                alert_id=f"alert_{i}",
                agent_type="TestAgent",
                alert_type=["monitoring", "database", "network", "kubernetes"][i % 4],
                status="completed",
                started_at_us=int((datetime.now(timezone.utc).timestamp() - i * 60) * 1_000_000),
                completed_at_us=int((datetime.now(timezone.utc).timestamp() - i * 60 + 30) * 1_000_000),
                alert_data=alert_data
            )
            repository.session.add(session)
        
        repository.session.commit()
        return repository
    
    @pytest.mark.unit
    def test_json_field_query_performance(self, repository_with_flexible_data):
        """Test performance of JSON field queries with complex data structures."""
        import time
        
        # Test 1: Query by severity (should use JSON index)
        start_time = time.time()
        sessions = repository_with_flexible_data.get_alert_sessions(page_size=100)
        
        # Filter in Python to simulate JSON query (since SQLite doesn't have JSON indexes)
        critical_sessions = [
            s for s in sessions["sessions"]
            if s.alert_data and s.alert_data.get("severity") == "critical"
        ]
        
        query_time = time.time() - start_time
        
        # Should complete reasonably quickly (under 500ms for 100 records)
        assert query_time < 0.5, f"JSON severity query took {query_time:.3f}s, should be faster"
        assert len(critical_sessions) > 0, "Should find some critical alerts"
    
    @pytest.mark.unit  
    def test_complex_json_structure_performance(self, repository_with_flexible_data):
        """Test performance with complex nested JSON structures."""
        import time
        
        # Test querying nested data structures
        start_time = time.time()
        
        sessions = repository_with_flexible_data.get_alert_sessions(page_size=100)
        
        # Simulate complex JSON queries on nested data
        monitoring_with_high_cpu = []
        for session in sessions["sessions"]:
            if (session.alert_data and 
                session.alert_data.get("metrics") and
                isinstance(session.alert_data["metrics"], dict) and
                session.alert_data["metrics"].get("cpu_usage", 0) > 80):
                monitoring_with_high_cpu.append(session)
        
        query_time = time.time() - start_time
        
        # Should handle nested JSON queries reasonably
        assert query_time < 0.2, f"Complex JSON query took {query_time:.3f}s, should be faster"
        assert len(monitoring_with_high_cpu) >= 0, "Query should complete successfully"
    
    @pytest.mark.unit
    def test_json_array_query_performance(self, repository_with_flexible_data):
        """Test performance of querying JSON arrays within alert data."""
        import time
        
        start_time = time.time()
        
        sessions = repository_with_flexible_data.get_alert_sessions(page_size=100)
        
        # Query sessions with array data (labels, queries, events, etc.)
        sessions_with_arrays = []
        for session in sessions["sessions"]:
            if session.alert_data:
                # Check for any array fields
                has_arrays = any(
                    isinstance(v, list) for v in session.alert_data.values()
                ) or any(
                    isinstance(v, dict) and any(isinstance(nested_v, list) for nested_v in v.values())
                    for v in session.alert_data.values() if isinstance(v, dict)
                )
                
                if has_arrays:
                    sessions_with_arrays.append(session)
        
        query_time = time.time() - start_time
        
        # Should handle array queries efficiently
        assert query_time < 0.15, f"Array JSON query took {query_time:.3f}s, should be faster"
        assert len(sessions_with_arrays) > 0, "Should find sessions with array data"
    
    @pytest.mark.unit
    def test_json_pagination_performance(self, repository_with_flexible_data):
        """Test pagination performance with large JSON payloads."""
        import time
        
        # Test multiple pages to ensure consistent performance
        page_times = []
        
        for page in range(1, 6):  # Test 5 pages
            start_time = time.time()
            
            result = repository_with_flexible_data.get_alert_sessions(
                page=page,
                page_size=20
            )
            
            page_time = time.time() - start_time
            page_times.append(page_time)
            
            # Verify pagination works with flexible data
            assert len(result["sessions"]) <= 20
            assert result["pagination"]["page"] == page
        
        # Performance should be consistent across pages
        avg_page_time = sum(page_times) / len(page_times)
        max_page_time = max(page_times)
        
        assert avg_page_time < 0.05, f"Average page time {avg_page_time:.3f}s too slow"
        assert max_page_time < 0.1, f"Slowest page time {max_page_time:.3f}s too slow"
        
        # Performance shouldn't degrade significantly across pages
        first_page_time = page_times[0]
        last_page_time = page_times[-1]
        
        # Last page shouldn't be more than 3x slower than first page
        assert last_page_time < first_page_time * 3, \
            f"Performance degraded from {first_page_time:.3f}s to {last_page_time:.3f}s"
    

 
