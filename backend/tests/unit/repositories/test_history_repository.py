"""
Unit tests for HistoryRepository.

Tests the repository layer functionality with in-memory database to ensure
proper data access layer implementation and database operations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlmodel import Session, SQLModel, create_engine

from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
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
        from tarsy.utils.timestamp import now_us
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
            session_metadata={"test": "metadata"},
            chain_id="test-chain-123"
        )
    
    @pytest.fixture
    def sample_llm_interaction(self):
        """Create sample LLMInteraction for testing."""
        from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
        
        # Create conversation with proper message structure
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Analyze the namespace termination issue"),
            LLMMessage(role=MessageRole.ASSISTANT, content="The namespace is stuck due to finalizers")
        ])
        
        return LLMInteraction(
            session_id="test-session-123",
            model_name="gpt-4",
            step_description="Initial analysis",
            conversation=conversation,
            duration_ms=1500,
            success=True
        )
    
    @pytest.fixture
    def sample_failed_llm_interaction(self):
        """Create sample failed LLM interaction for testing."""
        from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
        
        # Create conversation with request messages only (no assistant response since it failed)
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Analyze the namespace termination issue")
        ])
        
        return LLMInteraction(
            session_id="test-session-123",
            model_name="gemini-1.5-pro",
            step_description="Failed analysis due to rate limiting",
            conversation=conversation,
            duration_ms=500,
            success=False,
            error_message="Resource has been exhausted (e.g. check quota). Error 429: Quota exceeded for requests"
        )
    
    @pytest.fixture
    def sample_mcp_communication(self):
        """Create sample MCPInteraction for testing."""
        return MCPInteraction(
            communication_id="mcp-comm-101",
            session_id="test-session-123",
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get_namespace",
            tool_arguments={"namespace": "stuck-namespace"},
            tool_result={"status": "Terminating", "finalizers": ["test-finalizer"]},
            timestamp_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            step_description="Check namespace status",
            duration_ms=800,
            success=True
        )
    
    @pytest.mark.parametrize("session_id,expected_result", [
        ("test-session-123", "found"),
        ("non-existent-session", None),
    ])
    def test_alert_session_retrieval(self, repository, sample_alert_session, session_id, expected_result):
        """Test alert session creation and retrieval scenarios."""
        if expected_result == "found":
            # Create session first
            created_session = repository.create_alert_session(sample_alert_session)
            assert created_session.session_id == sample_alert_session.session_id
            
            # Verify session was saved to database
            retrieved_session = repository.get_alert_session(session_id)
            assert retrieved_session is not None
            assert retrieved_session.alert_id == sample_alert_session.alert_id
            assert retrieved_session.agent_type == sample_alert_session.agent_type
            assert retrieved_session.status == sample_alert_session.status
        else:
            # Test getting non-existent session
            session = repository.get_alert_session(session_id)
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
        assert interactions[0].model_name == sample_llm_interaction.model_name
        assert interactions[0].step_description == sample_llm_interaction.step_description
    
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
            started_at_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            completed_at_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            chain_id="test-chain-456"
        )
        repository.create_alert_session(session2)
        
        # Test status filter
        result = repository.get_alert_sessions(status="completed")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session2.session_id
        
        # Test agent_type filter
        result = repository.get_alert_sessions(agent_type="KubernetesAgent")
        assert len(result.sessions) == 2
        
        # Test alert_type filter
        result = repository.get_alert_sessions(alert_type="NamespaceTerminating")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_date_filters(self, repository):
        """Test getting alert sessions with date range filters."""
        # Create sessions with different timestamps
        from tarsy.utils.timestamp import now_us
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
            completed_at_us=five_days_ago_us,
            chain_id="test-chain-old"
        )
        
        new_session = AlertSession(
            session_id="new-session",
            alert_id="new-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at_us=one_hour_ago_us,
            completed_at_us=one_hour_ago_us,
            chain_id="test-chain-new"
        )
        
        repository.create_alert_session(old_session)
        repository.create_alert_session(new_session)
        
        # Test start_date filter (convert unix timestamp back to datetime for current API)
        two_days_ago_us = now_us_time - (2 * 24 * 60 * 60 * 1000000)  # 2 days in microseconds
        result = repository.get_alert_sessions(start_date_us=two_days_ago_us)
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == new_session.session_id
        
        # Test end_date_us filter
        result = repository.get_alert_sessions(end_date_us=two_days_ago_us)
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == old_session.session_id
    
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
                started_at_us=int((datetime.now(timezone.utc) - timedelta(minutes=i)).timestamp() * 1_000_000),
                chain_id=f"test-chain-{i}"
            )
            repository.create_alert_session(session)
        
        # Test first page
        result = repository.get_alert_sessions(page=1, page_size=2)
        assert len(result.sessions) == 2
        assert result.pagination.page == 1
        assert result.pagination.page_size == 2
        assert result.pagination.total_items == 5
        assert result.pagination.total_pages == 3
        
        # Test second page
        result = repository.get_alert_sessions(page=2, page_size=2)
        assert len(result.sessions) == 2
        assert result.pagination.page == 2
        
        # Test last page
        result = repository.get_alert_sessions(page=3, page_size=2)
        assert len(result.sessions) == 1
        assert result.pagination.page == 3
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_error_message(self, repository):
        """Test search functionality in error_message field."""
        from tarsy.utils.timestamp import now_us
        
        # Create sessions with different error messages
        session1 = AlertSession(
            session_id="test-session-search-1",
            alert_id="alert-search-1",
            alert_data={"alert_type": "NetworkError"},
            agent_type="NetworkAgent",
            alert_type="NetworkError",
            status="failed",
            started_at_us=now_us(),
            error_message="Connection refused by kubernetes API server",
            chain_id="test-chain-search-1"
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
            error_message="Timeout occurred while querying database",
            chain_id="test-chain-search-2"
        )
        repository.create_alert_session(session2)
        
        # Test search in error messages
        result = repository.get_alert_sessions(search="kubernetes")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="timeout")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session2.session_id
        
        result = repository.get_alert_sessions(search="connection")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_final_analysis(self, repository):
        """Test search functionality in final_analysis field."""
        from tarsy.utils.timestamp import now_us
        
        # Create sessions with different analyses
        session1 = AlertSession(
            session_id="test-session-analysis-1",
            alert_id="alert-analysis-1", 
            alert_data={"alert_type": "NamespaceTerminating"},
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="completed",
            started_at_us=now_us(),
            final_analysis="The namespace is stuck because of finalizer blocking deletion. Use kubectl patch to remove finalizer.",
            chain_id="test-chain-analysis-1"
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
            final_analysis="Pod is crashing due to memory limits. Increase resource requests and limits in deployment.",
            chain_id="test-chain-analysis-2"
        )
        repository.create_alert_session(session2)
        
        # Test search in final analysis
        result = repository.get_alert_sessions(search="finalizer")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="memory")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session2.session_id
        
        result = repository.get_alert_sessions(search="kubectl")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_alert_data_fields(self, repository):
        """Test search functionality in JSON alert_data fields."""
        from tarsy.utils.timestamp import now_us
        
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
            started_at_us=now_us(),
            chain_id="test-chain-json-1"
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
            started_at_us=now_us(),
            chain_id="test-chain-json-2"
        )
        repository.create_alert_session(session2)
        
        # Test search in different JSON fields
        result = repository.get_alert_sessions(search="superman")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="finalizers")  
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="cpu")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session2.session_id
        
        result = repository.get_alert_sessions(search="production")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="critical")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        result = repository.get_alert_sessions(search="staging")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session2.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_case_insensitive(self, repository):
        """Test that search is case-insensitive."""
        from tarsy.utils.timestamp import now_us
        
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
            error_message="Connection failed to API Server",
            chain_id="test-chain-case-1"
        )
        repository.create_alert_session(session)
        
        # Test case insensitive search
        result = repository.get_alert_sessions(search="kubernetes")  # lowercase
        assert len(result.sessions) == 1
        
        result = repository.get_alert_sessions(search="KUBERNETES")  # uppercase
        assert len(result.sessions) == 1
        
        result = repository.get_alert_sessions(search="KuBeRnEtEs")  # mixed case
        assert len(result.sessions) == 1
        
        result = repository.get_alert_sessions(search="production")  # lowercase environment
        assert len(result.sessions) == 1
        
        result = repository.get_alert_sessions(search="api server")  # lowercase error message
        assert len(result.sessions) == 1
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_combined_with_filters(self, repository):
        """Test search functionality combined with other filters."""
        from tarsy.utils.timestamp import now_us
        
        session1 = AlertSession(
            session_id="test-session-combined-1",
            alert_id="alert-combined-1",
            alert_data={"message": "Kubernetes namespace issue"},
            agent_type="KubernetesAgent",
            alert_type="NamespaceTerminating",
            status="completed",
            started_at_us=now_us(),
            chain_id="test-chain-combined-1"
        )
        repository.create_alert_session(session1)
        
        session2 = AlertSession(
            session_id="test-session-combined-2", 
            alert_id="alert-combined-2",
            alert_data={"message": "Kubernetes pod issue"},
            agent_type="KubernetesAgent",
            alert_type="UnidledPods",
            status="failed",
            started_at_us=now_us(),
            chain_id="test-chain-combined-2"
        )
        repository.create_alert_session(session2)
        
        session3 = AlertSession(
            session_id="test-session-combined-3",
            alert_id="alert-combined-3", 
            alert_data={"message": "Database connection issue"},
            agent_type="DatabaseAgent",
            alert_type="ConnectionTimeout",
            status="completed",
            started_at_us=now_us(),
            chain_id="test-chain-combined-3"
        )
        repository.create_alert_session(session3)
        
        # Test search + status filter
        result = repository.get_alert_sessions(search="kubernetes", status="completed")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session1.session_id
        
        # Test search + agent_type filter
        result = repository.get_alert_sessions(search="issue", agent_type="KubernetesAgent")
        assert len(result.sessions) == 2
        session_ids = [s.session_id for s in result.sessions]
        assert session1.session_id in session_ids
        assert session2.session_id in session_ids
        
        # Test search + alert_type filter
        result = repository.get_alert_sessions(search="kubernetes", alert_type="UnidledPods")
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session2.session_id
    
    @pytest.mark.unit
    def test_get_alert_sessions_with_search_no_matches(self, repository):
        """Test search functionality when no matches are found."""
        from tarsy.utils.timestamp import now_us
        
        session = AlertSession(
            session_id="test-session-nomatch-1",
            alert_id="alert-nomatch-1",
            alert_data={"message": "Simple alert message"},
            agent_type="SimpleAgent",
            alert_type="SimpleAlert",
            status="completed",
            started_at_us=now_us(),
            chain_id="test-chain-nomatch-1"
        )
        repository.create_alert_session(session)
        
        # Test search that should return no results
        result = repository.get_alert_sessions(search="nonexistent")
        assert len(result.sessions) == 0
        assert result.pagination.total_items == 0
        
        result = repository.get_alert_sessions(search="kubernetes")  # Not in any field
        assert len(result.sessions) == 0
        assert result.pagination.total_items == 0
    
    @pytest.mark.unit
    def test_get_session_details_chronological_order(self, repository, sample_alert_session):
        """Test session timeline reconstruction with chronological ordering."""
        from tarsy.models.db_models import StageExecution
        from tarsy.utils.timestamp import now_us
        
        # Create session
        repository.create_alert_session(sample_alert_session)
        
        # Create a stage execution first (interactions must belong to a stage)
        stage_execution = StageExecution(
            session_id=sample_alert_session.session_id,
            stage_id="initial-analysis",
            stage_index=0,
            stage_name="Initial Analysis",
            agent="KubernetesAgent",
            status="completed",
            started_at_us=now_us(),
            completed_at_us=now_us() + 5000000,  # 5 seconds later
            duration_ms=5000
        )
        stage_execution_id = repository.create_stage_execution(stage_execution)
        
        # Create interactions and communications with specific timestamps
        base_time = datetime.now(timezone.utc)
        
        llm1 = LLMInteraction(
            session_id=sample_alert_session.session_id,
            model_name="gpt-4",
            step_description="First LLM interaction",
            request_json={"messages": [{"role": "user", "content": "First prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "First response"}, "finish_reason": "stop"}]},
            timestamp_us=int(base_time.timestamp() * 1_000_000),
            stage_execution_id=stage_execution_id
        )
        
        mcp1 = MCPInteraction(
            communication_id="mcp-1",
            session_id=sample_alert_session.session_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get",
            timestamp_us=int((base_time + timedelta(seconds=1)).timestamp() * 1_000_000),
            step_description="First MCP call",
            success=True,
            stage_execution_id=stage_execution_id
        )
        
        llm2 = LLMInteraction(
            session_id=sample_alert_session.session_id,
            model_name="gpt-4",
            step_description="Second LLM interaction",
            request_json={"messages": [{"role": "user", "content": "Second prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Second response"}, "finish_reason": "stop"}]},
            timestamp_us=int((base_time + timedelta(seconds=2)).timestamp() * 1_000_000),
            stage_execution_id=stage_execution_id
        )
        
        repository.create_llm_interaction(llm1)
        repository.create_mcp_communication(mcp1)
        repository.create_llm_interaction(llm2)
        
        # Get timeline
        timeline = repository.get_session_details(sample_alert_session.session_id)
        
        assert timeline is not None
        assert timeline.session_id == sample_alert_session.session_id
        assert len(timeline.stages) > 0
        
        # Collect all interactions from all stages for chronological verification
        all_interactions = []
        for stage in timeline.stages:
            all_interactions.extend(stage.llm_interactions)
            all_interactions.extend(stage.mcp_communications)
        
        # Sort by timestamp for chronological order verification
        all_interactions.sort(key=lambda x: x.timestamp_us)
        
        assert len(all_interactions) == 3
        assert all_interactions[0].type == "llm"
        assert all_interactions[1].type == "mcp"  
        assert all_interactions[2].type == "llm"
        
        # Verify timeline is ordered by timestamp_us
        for i in range(len(all_interactions) - 1):
            assert all_interactions[i].timestamp_us <= all_interactions[i + 1].timestamp_us

    @pytest.mark.unit
    def test_get_session_details_unix_timestamp_precision(self, repository, sample_alert_session):
        """Test session timeline with Unix timestamp precision and chronological ordering."""
        from tarsy.models.db_models import StageExecution
        from tarsy.utils.timestamp import now_us
        
        # Create session
        repository.create_alert_session(sample_alert_session)
        
        # Create stage execution first (interactions must belong to a stage)
        stage_execution = StageExecution(
            session_id=sample_alert_session.session_id,
            stage_id="timestamp-precision-test",
            stage_index=0,
            stage_name="Timestamp Precision Test",
            agent="TestAgent",
            status="completed",
            started_at_us=now_us(),
            completed_at_us=now_us() + 10000000,  # 10 seconds later
            duration_ms=10000
        )
        stage_execution_id = repository.create_stage_execution(stage_execution)
        
        # Create interactions with specific Unix timestamps (microseconds since epoch)
        base_timestamp_us = 1705314645123456  # 2024-01-15T10:30:45.123456Z UTC
        
        # Create LLM interaction with precise timestamp
        llm_interaction = LLMInteraction(
            session_id=sample_alert_session.session_id,
            model_name="gpt-4",
            step_description="LLM interaction with precise timestamp",
            request_json={"messages": [{"role": "user", "content": "Precise timestamp prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Precise timestamp response"}, "finish_reason": "stop"}]},
            timestamp_us=base_timestamp_us,
            stage_execution_id=stage_execution_id
        )
        
        # Create MCP communication 1 second later
        mcp_communication = MCPInteraction(
            communication_id="mcp-later",
            session_id=sample_alert_session.session_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get",
            timestamp_us=base_timestamp_us + 1_000_000,  # 1 second later
            step_description="MCP call 1 second later",
            success=True,
            stage_execution_id=stage_execution_id
        )
        
        # Create another LLM interaction 500ms after first
        llm_interaction_middle = LLMInteraction(
            session_id=sample_alert_session.session_id,
            model_name="gpt-4",
            step_description="LLM interaction in middle",
            request_json={"messages": [{"role": "user", "content": "Middle timestamp prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Middle timestamp response"}, "finish_reason": "stop"}]},
            timestamp_us=base_timestamp_us + 500_000,  # 500ms later
            stage_execution_id=stage_execution_id
        )
        
        repository.create_llm_interaction(llm_interaction)
        repository.create_mcp_communication(mcp_communication)
        repository.create_llm_interaction(llm_interaction_middle)
        
        # Get timeline
        timeline = repository.get_session_details(sample_alert_session.session_id)
        
        assert timeline is not None
        
        # Collect all interactions from stages and sort chronologically
        all_interactions = []
        for stage in timeline.stages:
            all_interactions.extend(stage.llm_interactions)
            all_interactions.extend(stage.mcp_communications)
        
        all_interactions.sort(key=lambda x: x.timestamp_us)
        assert len(all_interactions) == 3
        
        # Verify chronological ordering by timestamp_us
        assert all_interactions[0].type == "llm"
        assert all_interactions[1].type == "llm"
        assert all_interactions[2].type == "mcp"
        
        # Verify Unix timestamps are preserved for sorting
        assert all_interactions[0].timestamp_us == base_timestamp_us
        assert all_interactions[1].timestamp_us == base_timestamp_us + 500_000
        assert all_interactions[2].timestamp_us == base_timestamp_us + 1_000_000
        
        # Verify Unix timestamps are returned as integers
        assert all_interactions[0].timestamp_us == base_timestamp_us
        assert all_interactions[1].timestamp_us == base_timestamp_us + 500_000  # +500ms
        assert all_interactions[2].timestamp_us == base_timestamp_us + 1_000_000  # +1s
        
        # Verify all timestamp_us values are integers
        for interaction in all_interactions:
            assert isinstance(interaction.timestamp_us, int)
            assert interaction.timestamp_us > 0

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
            started_at_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            chain_id="test-chain-active"
        )
        
        completed_session = AlertSession(
            session_id="completed-session",
            alert_id="completed-alert",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test",
            status="completed",
            started_at_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            completed_at_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            chain_id="test-chain-completed"
        )
        
        repository.create_alert_session(active_session)
        repository.create_alert_session(completed_session)
        
        # Get active sessions
        active_sessions = repository.get_active_sessions()
        
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == active_session.session_id
        assert active_sessions[0].status == "in_progress"

    @pytest.mark.unit
    def test_get_session_details_empty_session(self, repository):
        """Test getting timeline for non-existent session."""
        result = repository.get_session_details("non-existent-session")
        assert result is None

    @pytest.mark.unit
    def test_get_llm_interactions_empty_session(self, repository):
        """Test getting LLM interactions for non-existent session."""
        interactions = repository.get_llm_interactions_for_session("non-existent-session")
        assert interactions == []

    @pytest.mark.unit
    def test_get_mcp_communications_empty_session(self, repository):
        """Test getting MCP communications for non-existent session."""
        communications = repository.get_mcp_communications_for_session("non-existent-session")
        assert communications == []

    @pytest.mark.unit
    def test_create_alert_session_duplicate_prevention(self, repository, sample_alert_session):
        """Test that creating duplicate alert sessions is prevented."""
        # Create the first session
        first_result = repository.create_alert_session(sample_alert_session)
        assert first_result is not None
        assert first_result.session_id == sample_alert_session.session_id

        # Attempt to create the same session again (same alert_id)
        duplicate_session = AlertSession(
            session_id="different-session-id",  # Different session_id
            alert_id=sample_alert_session.alert_id,  # Same alert_id - should trigger duplicate prevention
            alert_data=sample_alert_session.alert_data,
            agent_type=sample_alert_session.agent_type,
            alert_type=sample_alert_session.alert_type,
            status=sample_alert_session.status,
            started_at_us=sample_alert_session.started_at_us,
            chain_id="test-chain-duplicate"
        )
        
        # Should return the existing session, not create a new one
        second_result = repository.create_alert_session(duplicate_session)
        assert second_result is not None
        assert second_result.session_id == sample_alert_session.session_id  # Should return original
        assert second_result.alert_id == sample_alert_session.alert_id

    @pytest.mark.unit
    def test_get_alert_sessions_edge_cases(self, repository):
        """Test edge cases for get_alert_sessions method."""
        # Test with empty database
        result = repository.get_alert_sessions()
        assert result.sessions == []
        assert result.pagination.total_items == 0
        assert result.pagination.total_pages == 0

        # Test with invalid page numbers
        result = repository.get_alert_sessions(page=0)  # Should handle gracefully
        assert result.sessions == []

        result = repository.get_alert_sessions(page=-1)  # Should handle gracefully  
        assert result.sessions == []

        # Test with very large page size
        result = repository.get_alert_sessions(page_size=10000)
        assert result.sessions == []

    @pytest.mark.unit  
    def test_get_alert_sessions_multiple_status_list(self, repository):
        """Test filtering by multiple status values using list."""
        # Create sessions with different statuses
        statuses = ["pending", "in_progress", "completed", "failed"]
        
        for i, status in enumerate(statuses):
            session = AlertSession(
                session_id=f"multi-status-{i}",
                alert_id=f"alert-multi-{i}",
                alert_data={},
                agent_type="TestAgent",
                alert_type="TestAlert",
                status=status,
                started_at_us=int((datetime.now(timezone.utc) - timedelta(minutes=i)).timestamp() * 1_000_000),
                chain_id=f"test-chain-multi-{i}"
            )
            repository.create_alert_session(session)

        # Test filtering by multiple statuses
        result = repository.get_alert_sessions(status=["pending", "in_progress"])
        assert len(result.sessions) == 2
        session_statuses = [s.status for s in result.sessions]
        # Convert enum objects to strings for comparison
        session_status_values = [status.value if hasattr(status, 'value') else status for status in session_statuses]
        assert "pending" in session_status_values
        assert "in_progress" in session_status_values
        assert "completed" not in session_status_values
        assert "failed" not in session_status_values
        
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
                started_at_us=int(started_at.timestamp() * 1_000_000),
                completed_at_us=int((started_at + timedelta(minutes=10)).timestamp() * 1_000_000) if status == "completed" else None,
                chain_id=f"test-chain-{session_id}"
            )
            repository.create_alert_session(session)
        
        # Test alert_type + status combination
        result = repository.get_alert_sessions(
            alert_type="NamespaceTerminating",
            status="completed"
        )
        assert len(result.sessions) == 2  # session-1 and session-4
        
        # Test alert_type + status + agent_type combination
        result = repository.get_alert_sessions(
            alert_type="NamespaceTerminating",
            status="completed",
            agent_type="KubernetesAgent"
        )
        assert len(result.sessions) == 1  # only session-1
        assert result.sessions[0].session_id == "session-1"
        
        # Test agent_type + status + time_range combination
        result = repository.get_alert_sessions(
            agent_type="KubernetesAgent",
            status="completed",
            start_date_us=int((now - timedelta(hours=3.5)).timestamp() * 1_000_000)  # Should get session-1 and session-3
        )
        assert len(result.sessions) == 2
        session_ids = [s.session_id for s in result.sessions]
        assert "session-1" in session_ids
        assert "session-3" in session_ids

    @pytest.mark.unit
    def test_create_successful_llm_interaction(self, repository, sample_alert_session, sample_llm_interaction):
        """Test creating successful LLM interaction with success=True."""
        # Create session first
        repository.create_alert_session(sample_alert_session)
        
        # Create successful interaction
        created_interaction = repository.create_llm_interaction(sample_llm_interaction)
        
        assert created_interaction.interaction_id == sample_llm_interaction.interaction_id
        assert created_interaction.success == True
        assert created_interaction.error_message is None
        
        # Verify interaction was saved with correct success status
        interactions = repository.get_llm_interactions_for_session(sample_alert_session.session_id)
        assert len(interactions) == 1
        assert interactions[0].success == True
        assert interactions[0].error_message is None
        assert interactions[0].conversation is not None
        assert len(interactions[0].conversation.messages) == 3  # system + user + assistant

    @pytest.mark.unit
    def test_create_failed_llm_interaction(self, repository, sample_alert_session, sample_failed_llm_interaction):
        """Test creating failed LLM interaction with success=False and error_message."""
        # Create session first
        repository.create_alert_session(sample_alert_session)
        
        # Create failed interaction
        created_interaction = repository.create_llm_interaction(sample_failed_llm_interaction)
        
        assert created_interaction.interaction_id == sample_failed_llm_interaction.interaction_id
        assert created_interaction.success == False
        assert created_interaction.error_message is not None
        assert "429" in created_interaction.error_message
        assert "Quota exceeded" in created_interaction.error_message
        
        # Verify interaction was saved with correct failure status
        interactions = repository.get_llm_interactions_for_session(sample_alert_session.session_id)
        assert len(interactions) == 1
        assert interactions[0].success == False
        assert interactions[0].error_message == sample_failed_llm_interaction.error_message
        assert interactions[0].conversation is not None
        assert len(interactions[0].conversation.messages) == 2  # system + user only (no assistant response for failed)

    @pytest.mark.unit
    def test_get_session_details_includes_success_error_fields(self, repository, sample_alert_session):
        """Test session timeline includes success and error_message fields in LLM interactions."""
        from tarsy.models.db_models import StageExecution
        from tarsy.utils.timestamp import now_us
        
        # Create session
        repository.create_alert_session(sample_alert_session)
        
        # Create stage execution first (interactions must belong to a stage)
        stage_execution = StageExecution(
            session_id=sample_alert_session.session_id,
            stage_id="success-error-test",
            stage_index=0,
            stage_name="Success/Error Test Stage",
            agent="TestAgent",
            status="completed",
            started_at_us=now_us(),
            completed_at_us=now_us() + 5000000,  # 5 seconds later
            duration_ms=5000
        )
        stage_execution_id = repository.create_stage_execution(stage_execution)
        
        # Create successful interaction
        successful_interaction = LLMInteraction(
            session_id=sample_alert_session.session_id,
            model_name="gpt-4",
            step_description="Successful analysis",
            request_json={"messages": [{"role": "user", "content": "Test prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Test response"}, "finish_reason": "stop"}]},
            duration_ms=1000,
            success=True,
            stage_execution_id=stage_execution_id
        )
        
        # Create failed interaction
        failed_interaction = LLMInteraction(
            session_id=sample_alert_session.session_id,
            model_name="gemini-1.5-pro",
            step_description="Failed analysis",
            request_json={"messages": [{"role": "user", "content": "Test prompt"}]},
            response_json=None,
            duration_ms=500,
            success=False,
            error_message="API rate limit exceeded",
            stage_execution_id=stage_execution_id
        )
        
        repository.create_llm_interaction(successful_interaction)
        repository.create_llm_interaction(failed_interaction)
        
        # Get timeline
        timeline = repository.get_session_details(sample_alert_session.session_id)
        
        assert timeline is not None
        assert len(timeline.stages) > 0
        
        # Collect all LLM interactions from stages
        llm_interactions = []
        for stage in timeline.stages:
            llm_interactions.extend(stage.llm_interactions)
        
        assert len(llm_interactions) == 2
        
        # Find the successful and failed interactions
        successful_interaction = None
        failed_interaction = None
        
        for interaction in llm_interactions:
            if interaction.details.success == True:
                successful_interaction = interaction
            elif interaction.details.success == False:
                failed_interaction = interaction
        
        # Verify successful interaction details
        assert successful_interaction is not None
        assert successful_interaction.details.success == True
        assert successful_interaction.details.error_message is None
        
        # Verify failed interaction details
        assert failed_interaction is not None
        assert failed_interaction.details.success == False
        assert failed_interaction.details.error_message == "API rate limit exceeded"

    @pytest.mark.unit
    def test_mixed_successful_and_failed_interactions_in_session(self, repository, sample_alert_session):
        """Test session with mix of successful and failed LLM interactions."""
        # Create session
        repository.create_alert_session(sample_alert_session)
        
        # Create multiple interactions with different success statuses
        interactions = [
            LLMInteraction(
                session_id=sample_alert_session.session_id,
                model_name="gpt-4",
                step_description="First attempt - successful",
                request_json={"messages": [{"role": "user", "content": "Analyze issue"}]},
                response_json={"choices": [{"message": {"role": "assistant", "content": "Analysis complete"}, "finish_reason": "stop"}]},
                duration_ms=1200,
                success=True
            ),
            LLMInteraction(
                session_id=sample_alert_session.session_id,
                model_name="gemini-1.5-pro",
                step_description="Second attempt - failed",
                request_json={"messages": [{"role": "user", "content": "Follow up analysis"}]},
                response_json=None,
                duration_ms=300,
                success=False,
                error_message="Connection timeout"
            ),
            LLMInteraction(
                session_id=sample_alert_session.session_id,
                model_name="gpt-4",
                step_description="Third attempt - successful",
                request_json={"messages": [{"role": "user", "content": "Final analysis"}]},
                response_json={"choices": [{"message": {"role": "assistant", "content": "Final conclusion"}, "finish_reason": "stop"}]},
                duration_ms=900,
                success=True
            )
        ]
        
        for interaction in interactions:
            repository.create_llm_interaction(interaction)
        
        # Verify all interactions were saved correctly
        saved_interactions = repository.get_llm_interactions_for_session(sample_alert_session.session_id)
        assert len(saved_interactions) == 3
        
        # Verify success statuses
        success_count = sum(1 for i in saved_interactions if i.success)
        failure_count = sum(1 for i in saved_interactions if not i.success)
        
        assert success_count == 2
        assert failure_count == 1
        
        # Verify error messages
        failed_interactions = [i for i in saved_interactions if not i.success]
        assert len(failed_interactions) == 1
        assert failed_interactions[0].error_message == "Connection timeout"

    @pytest.mark.unit
    def test_update_stage_execution_success(self, repository, sample_alert_session):
        """Test successful stage execution update."""
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        # Create session first
        repository.create_alert_session(sample_alert_session)
        
        # Create a stage execution
        stage_execution = StageExecution(
            execution_id="test-stage-123",
            session_id=sample_alert_session.session_id,
            stage_id="initial-analysis",
            stage_index=0,
            stage_name="Initial Analysis",
            agent="KubernetesAgent",
            status=StageStatus.ACTIVE.value,
            started_at_us=now_us()
        )
        
        # First create the stage execution
        repository.session.add(stage_execution)
        repository.session.commit()
        repository.session.refresh(stage_execution)
        
        # Now update it to completed
        stage_execution.status = StageStatus.COMPLETED.value
        stage_execution.completed_at_us = now_us()
        stage_execution.duration_ms = 5000
        stage_execution.stage_output = {"result": "analysis complete"}
        
        # Update the stage execution
        result = repository.update_stage_execution(stage_execution)
        assert result == True
        
        # Verify the update was applied
        updated_execution = repository.session.get(StageExecution, stage_execution.execution_id)
        assert updated_execution.status == StageStatus.COMPLETED.value
        assert updated_execution.completed_at_us is not None
        assert updated_execution.duration_ms == 5000
        assert updated_execution.stage_output == {"result": "analysis complete"}

    @pytest.mark.unit
    def test_update_stage_execution_not_found(self, repository):
        """Test updating a non-existent stage execution raises ValueError."""
        from tarsy.models.constants import StageStatus
        
        # Create a stage execution with non-existent ID
        stage_execution = StageExecution(
            execution_id="non-existent-id",
            session_id="some-session",
            stage_id="test-stage",
            stage_index=0,
            stage_name="Test Stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED.value
        )
        
        # Attempt to update should raise ValueError
        with pytest.raises(ValueError, match="Stage execution with id non-existent-id not found"):
            repository.update_stage_execution(stage_execution)


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
            started_at_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
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
        assert result.sessions == []
        assert result.pagination.total_items == 0
    
    @pytest.mark.unit
    def test_get_session_details_database_error(self, repository_with_session_error):
        """Test getting session timeline with database error."""
        result = repository_with_session_error.get_session_details("test-session")
        assert result is None

    @pytest.mark.unit
    def test_update_alert_session_database_error(self, repository_with_session_error, sample_alert_session):
        """Test update alert session with database error."""
        result = repository_with_session_error.update_alert_session(sample_alert_session)
        assert result == False

    @pytest.mark.unit
    def test_get_llm_interactions_database_error(self, repository_with_session_error):
        """Test getting LLM interactions with database error."""
        with pytest.raises(Exception):
            repository_with_session_error.get_llm_interactions_for_session("test-session")

    @pytest.mark.unit
    def test_get_mcp_communications_database_error(self, repository_with_session_error):
        """Test getting MCP communications with database error."""
        with pytest.raises(Exception):
            repository_with_session_error.get_mcp_communications_for_session("test-session")

    @pytest.mark.unit
    def test_get_active_sessions_database_error(self, repository_with_session_error):
        """Test getting active sessions with database error."""
        with pytest.raises(Exception):
            repository_with_session_error.get_active_sessions()

    @pytest.mark.unit
    def test_get_filter_options_database_error(self, repository_with_session_error):
        """Test getting filter options with database error."""
        result = repository_with_session_error.get_filter_options()
        # Should return default structure with empty lists on error
        assert result.agent_types == []
        assert result.alert_types == []
        assert result.status_options == ["pending", "in_progress", "completed", "failed"]
        assert len(result.time_ranges) == 5

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
                started_at_us=int((now - timedelta(minutes=i)).timestamp() * 1_000_000),
                completed_at_us=int((now - timedelta(minutes=i-5)).timestamp() * 1_000_000) if i % 2 == 0 else None,
                chain_id=f"test-chain-perf-{i}"
            )
            repository.create_alert_session(session)
            
            # Add some interactions for every 10th session
            if i % 10 == 0:
                interaction = LLMInteraction(
                    session_id=session.session_id,
                    model_name="gpt-4",
                    step_description=f"Interaction {i}",
                    request_json={"messages": [{"role": "user", "content": f"Prompt {i}"}]},
                    response_json={"choices": [{"message": {"role": "assistant", "content": f"Response {i}"}, "finish_reason": "stop"}]},
                    timestamp_us=int((now - timedelta(minutes=i-1)).timestamp() * 1_000_000)
                )
                repository.create_llm_interaction(interaction)
        
        return repository
    
    @pytest.mark.unit
    def test_pagination_performance_large_dataset(self, repository_with_large_dataset):
        """Test pagination performance with large dataset."""
        # Test that pagination works efficiently with large dataset
        result = repository_with_large_dataset.get_alert_sessions(page=1, page_size=10)
        
        assert len(result.sessions) == 10
        assert result.pagination.total_items == 100
        assert result.pagination.total_pages == 10
        
        # Test middle page
        result = repository_with_large_dataset.get_alert_sessions(page=5, page_size=10)
        assert len(result.sessions) == 10
        assert result.pagination.page == 5
    
    @pytest.mark.unit
    def test_filtering_performance_large_dataset(self, repository_with_large_dataset):
        """Test filtering performance with large dataset."""
        # Test status filter performance
        result = repository_with_large_dataset.get_alert_sessions(status="completed", page_size=100)
        assert len(result.sessions) == 50  # Half of the sessions
        
        # Test combined filters performance
        result = repository_with_large_dataset.get_alert_sessions(
            status="completed",
            alert_type="TestAlert0"
        )
        # Should get completed sessions with TestAlert0 (sessions 0, 10, 20, etc.)
        assert len(result.sessions) == 10

    # Dashboard-specific tests
    
    @pytest.mark.unit
    def test_get_filter_options_success(self, db_session):
        """Test successful filter options retrieval."""
        repo = HistoryRepository(db_session)
        
        # Create test data with different types
        sessions = [
            AlertSession(session_id="1", alert_id="a1", agent_type="kubernetes", alert_type="PodCrashLooping", status="in_progress", alert_data={}, chain_id="test-chain-1"),
            AlertSession(session_id="2", alert_id="a2", agent_type="network", alert_type="ServiceDown", status="completed", alert_data={}, chain_id="test-chain-2"),
            AlertSession(session_id="3", alert_id="a3", agent_type="database", alert_type="ConnectionTimeout", status="failed", alert_data={}, chain_id="test-chain-3")
        ]
        
        for session in sessions:
            db_session.add(session)
        db_session.commit()
        
        result = repo.get_filter_options()
        
        # Verify agent types (should include kubernetes, network, database)
        assert hasattr(result, 'agent_types')
        assert len(result.agent_types) == 3
        assert "kubernetes" in result.agent_types
        assert "network" in result.agent_types
        assert "database" in result.agent_types
        
        # Verify alert types
        assert hasattr(result, 'alert_types')
        assert len(result.alert_types) == 3
        assert "PodCrashLooping" in result.alert_types
        assert "ServiceDown" in result.alert_types
        assert "ConnectionTimeout" in result.alert_types
        
        # Verify status options
        assert hasattr(result, 'status_options')
        assert len(result.status_options) == 4
        assert "pending" in result.status_options
        assert "in_progress" in result.status_options
        assert "completed" in result.status_options
        assert "failed" in result.status_options
        
        # Verify time ranges
        assert hasattr(result, 'time_ranges')
        assert len(result.time_ranges) == 5
    
    @pytest.mark.unit
    def test_get_filter_options_empty_database(self, db_session):
        """Test filter options with empty database."""
        repo = HistoryRepository(db_session)
        
        result = repo.get_filter_options()
        
        # Should return empty lists for dynamic options
        assert result.agent_types == []
        assert result.alert_types == []
        # Status options should always return all possible statuses (not dynamic from database)
        assert len(result.status_options) == 4
        assert result.status_options == ["pending", "in_progress", "completed", "failed"]
        
        # Time ranges should still be present (static)
        assert len(result.time_ranges) == 5
    
    @pytest.mark.unit
    def test_get_filter_options_sorted_results(self, db_session):
        """Test that filter options are properly sorted."""
        repo = HistoryRepository(db_session)
        
        # Create test data in non-alphabetical order
        sessions = [
            AlertSession(session_id="1", alert_id="a1", agent_type="zebra", alert_type="ZAlert", status="pending", alert_data={}, chain_id="test-chain-sort-1"),
            AlertSession(session_id="2", alert_id="a2", agent_type="alpha", alert_type="AAlert", status="completed", alert_data={}, chain_id="test-chain-sort-2"),
            AlertSession(session_id="3", alert_id="a3", agent_type="beta", alert_type="BAlert", status="in_progress", alert_data={}, chain_id="test-chain-sort-3")
        ]
        
        for session in sessions:
            db_session.add(session)
        db_session.commit()
        
        result = repo.get_filter_options()
        
        # Verify sorting
        assert result.agent_types == sorted(result.agent_types)
        assert result.alert_types == sorted(result.alert_types)
        # Status options are returned in constant definition order (not sorted)
        assert result.status_options == ["pending", "in_progress", "completed", "failed"]

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
                alert_data=alert_data,
                chain_id=f"test-chain-flex-{i}"
            )
            repository.session.add(session)
        
        repository.session.commit()
        return repository
    
    @pytest.mark.unit
    def test_json_field_query_functionality(self, repository_with_flexible_data):
        """Test functionality of JSON field queries with complex data structures."""
        # Get session list
        sessions = repository_with_flexible_data.get_alert_sessions(page_size=100)
        
        # Verify we get the expected number of sessions
        assert len(sessions.sessions) == 100, "Should retrieve all 100 test sessions"
        
        # Test JSON queries by getting full session details for each session
        critical_sessions = []
        for session_overview in sessions.sessions:
            session_id = session_overview.session_id
            # Get full session details (includes alert_data)
            full_session = repository_with_flexible_data.get_session_details(session_id)
            if full_session and full_session.alert_data:
                alert_data = full_session.alert_data
                if alert_data.get("severity") == "critical":
                    critical_sessions.append(full_session)
        
        # Verify filtering works and we get expected results
        assert len(critical_sessions) > 0, "Should find some critical alerts"
        
        # Verify all returned sessions actually have critical severity
        for session in critical_sessions:
            assert session.alert_data.get("severity") == "critical"
    
    @pytest.mark.unit  
    def test_complex_json_structure_functionality(self, repository_with_flexible_data):
        """Test functionality with complex nested JSON structures."""
        # Get session list
        sessions = repository_with_flexible_data.get_alert_sessions(page_size=100)
        
        # Verify we get all sessions
        assert len(sessions.sessions) == 100, "Should retrieve all 100 test sessions"
        
        # Test complex nested JSON queries by getting full session details
        monitoring_with_high_cpu = []
        for session_overview in sessions.sessions:
            session_id = session_overview.session_id
            # Get full session details (includes alert_data)
            full_session = repository_with_flexible_data.get_session_details(session_id)
            if full_session and full_session.alert_data:
                alert_data = full_session.alert_data
                if (alert_data.get("metrics") and
                    isinstance(alert_data["metrics"], dict) and
                    alert_data["metrics"].get("cpu_usage", 0) > 80):
                    monitoring_with_high_cpu.append(full_session)
        
        # Verify query completed successfully and found expected data
        assert len(monitoring_with_high_cpu) >= 0, "Query should complete successfully"
        
        # Verify all returned sessions actually have high CPU usage
        for session in monitoring_with_high_cpu:
            assert session.alert_data.get("metrics", {}).get("cpu_usage", 0) > 80
    
    @pytest.mark.unit
    def test_json_array_query_functionality(self, repository_with_flexible_data):
        """Test functionality of querying JSON arrays within alert data."""
        # Get session list
        sessions = repository_with_flexible_data.get_alert_sessions(page_size=100)
        
        # Verify we get all sessions
        assert len(sessions.sessions) == 100, "Should retrieve all 100 test sessions"
        
        # Query sessions with array data (labels, queries, events, etc.)
        sessions_with_arrays = []
        for session_overview in sessions.sessions:
            session_id = session_overview.session_id
            # Get full session details (includes alert_data)
            full_session = repository_with_flexible_data.get_session_details(session_id)
            if full_session and full_session.alert_data:
                alert_data = full_session.alert_data
                # Check for any array fields
                has_arrays = any(
                    isinstance(v, list) for v in alert_data.values()
                ) or any(
                    isinstance(v, dict) and any(isinstance(nested_v, list) for nested_v in v.values())
                    for v in alert_data.values() if isinstance(v, dict)
                )
                
                if has_arrays:
                    sessions_with_arrays.append(full_session)
        
        # Verify we found sessions with array data
        assert len(sessions_with_arrays) > 0, "Should find sessions with array data"
        
        # Verify all returned sessions actually have arrays
        for session in sessions_with_arrays:
            alert_data = session.alert_data
            has_arrays = any(
                isinstance(v, list) for v in alert_data.values()
            ) or any(
                isinstance(v, dict) and any(isinstance(nested_v, list) for nested_v in v.values())
                for v in alert_data.values() if isinstance(v, dict)
            )
            assert has_arrays, "Session should actually contain array data"
    
    @pytest.mark.unit
    def test_json_pagination_functionality(self, repository_with_flexible_data):
        """Test pagination functionality with large JSON payloads."""
        # Test multiple pages to ensure pagination works correctly
        total_sessions_seen = set()
        
        for page in range(1, 6):  # Test 5 pages
            result = repository_with_flexible_data.get_alert_sessions(
                page=page,
                page_size=20
            )
            
            # Verify pagination structure works correctly
            assert len(result.sessions) <= 20, f"Page {page} should have at most 20 sessions"
            assert result.pagination.page == page, "Page number should match request"
            assert result.pagination.page_size == 20, "Page size should match request"
            assert result.pagination.total_items == 100, "Total items should be consistent"
            assert result.pagination.total_pages == 5, "Total pages should be 5 for 100 items with page_size 20"
            
            # Track session IDs to ensure no duplicates across pages
            session_ids = {s.session_id for s in result.sessions}
            
            # Verify no duplicate sessions across pages
            overlap = total_sessions_seen.intersection(session_ids)
            assert len(overlap) == 0, f"Found duplicate sessions across pages: {overlap}"
            
            total_sessions_seen.update(session_ids)
        
        # Verify we covered all sessions across all pages
        assert len(total_sessions_seen) == 100, f"Should have seen all 100 unique sessions, but saw {len(total_sessions_seen)}"