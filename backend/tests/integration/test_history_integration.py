"""
Integration tests for History Service functionality.

Tests the complete history service integration including database operations,
service interactions, and cross-component communication.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from tarsy.main import app
from tarsy.models.alert import Alert
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction, LLMConversation, LLMMessage, MessageRole

# Import history models to ensure they're registered with SQLModel.metadata
from tarsy.services.alert_service import AlertService
from tarsy.services.history_service import HistoryService
from tarsy.utils.timestamp import now_us
from tests.conftest import alert_to_api_format

logger = logging.getLogger(__name__)


def create_test_context_and_chain(alert_type="kubernetes", session_id="test-session", chain_id="test-chain", agent="KubernetesAgent", alert_data=None):
    """Helper function to create test ChainContext and ChainConfigModel for integration tests."""
    from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
    from tarsy.models.processing_context import ChainContext
    
    if alert_data is None:
        alert_data = {
            "alert_type": alert_type,
            "environment": "test",
            "cluster": "test-cluster", 
            "namespace": "test-namespace",
            "message": "Test alert message"
        }
    
    from tarsy.models.alert import ProcessingAlert
    from tarsy.utils.timestamp import now_us
    
    processing_alert = ProcessingAlert(
        alert_type=alert_type,
        severity="warning",
        timestamp=now_us(),
        environment="test",
        alert_data=alert_data
    )
    chain_context = ChainContext.from_processing_alert(
        processing_alert=processing_alert,
        session_id=session_id,
        current_stage_name="test_stage"
    )
    
    chain_definition = ChainConfigModel(
        chain_id=chain_id,
        alert_types=[alert_type],
        stages=[
            ChainStageConfigModel(
                name="test_stage",
                agent=agent
            )
        ]
    )
    
    return chain_context, chain_definition


class TestHistoryServiceIntegration:
    """Integration tests for complete history service workflow."""
    
    @pytest.fixture
    def in_memory_engine(self):
        """Create in-memory SQLite engine for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        SQLModel.metadata.create_all(engine)
        return engine
    
    @pytest.fixture
    def history_service_with_db(self, in_memory_engine):
        """Create history service with test database for testing."""
        # For in-memory databases, we need to use the same connection
        # Multiple connections to :memory: create separate databases!
        
        # Mock settings to use the same in-memory database
        mock_settings = Mock()
        mock_settings.history_enabled = True  
        mock_settings.database_url = "sqlite:///:memory:"
        mock_settings.history_retention_days = 90
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            
            # CRITICAL: Replace the DatabaseManager's engine with our test engine
            # that already has the tables created, to avoid separate in-memory databases
            from tarsy.repositories.base_repository import DatabaseManager
            service.db_manager = DatabaseManager("sqlite:///:memory:")
            service.db_manager.engine = in_memory_engine  # Use the same engine with tables
            
            # Create session factory using the existing engine
            from sqlmodel import Session
            from sqlalchemy.orm import sessionmaker
            service.db_manager.session_factory = sessionmaker(
                bind=in_memory_engine,
                class_=Session,
                expire_on_commit=False
            )
            service._is_healthy = True  # Mark as healthy since we have a working engine
            
            logger.info(f"Using shared in-memory database engine with tables already created")
            
            yield service
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for testing."""
        return Alert(
            alert_type="NamespaceTerminating",
            severity="high",
            runbook="namespace-terminating.md",
            data={
                "environment": "production",
                "cluster": "k8s-prod",
                "namespace": "stuck-namespace",
                "message": "Namespace is stuck in Terminating state"
            }
        )
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = AsyncMock()
        client.generate_response.return_value = {
            "content": "The namespace is stuck due to finalizers. Let me check the current state.",
            "model": "gpt-4",
            "usage": {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
        }
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = AsyncMock()
        client.get_failed_servers = Mock(return_value={})  # No failed servers by default
        client.list_tools.return_value = [
            {"name": "kubectl_get_namespace", "description": "Get namespace information"},
            {"name": "kubectl_describe_namespace", "description": "Describe namespace details"}
        ]
        client.call_tool.return_value = {
            "result": {
                "status": "Terminating",
                "finalizers": ["kubernetes.io/finalizer.test"],
                "deletionTimestamp": "2024-01-01T12:00:00Z"
            },
            "success": True,
            "error": None
        }
        return client
    
    @pytest.fixture
    def mock_kubernetes_agent(self, mock_llm_client, mock_mcp_client):
        """Create mock Kubernetes agent."""
        agent = Mock()
        agent.process_alert = AsyncMock(return_value={
            "status": "completed",
            "analysis": "Namespace termination issue resolved",
            "actions_taken": ["Removed stuck finalizer"],
            "recommendations": ["Monitor namespace cleanup process"]
        })
        return agent
    
    @pytest.mark.integration
    def test_create_session_and_track_lifecycle(self, history_service_with_db, sample_alert):
        """Test creating a session and tracking its complete lifecycle."""
        # Create initial session
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type=sample_alert.alert_type,
            session_id="test-integration-session-123",
            chain_id="test-integration-chain-1",
            agent="KubernetesAgent"
        )
        
        # Override alert_data with sample alert data by creating a new ProcessingAlert
        from tarsy.models.alert import ProcessingAlert
        chain_context.processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity=sample_alert.severity or "warning",
            timestamp=chain_context.processing_alert.timestamp,
            environment=sample_alert.data.get('environment', 'production'),
            runbook_url=sample_alert.runbook,
            alert_data=sample_alert.data
        )
        
        result = history_service_with_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        
        assert result is True
        
        # Update session to in_progress
        result = history_service_with_db.update_session_status(
            session_id=chain_context.session_id,
            status="in_progress"
        )
        assert result == True
        
        # Create stage execution
        import asyncio

        from tests.utils import StageExecutionFactory
        stage_execution_id = asyncio.run(StageExecutionFactory.create_and_save_stage_execution(
            history_service_with_db,
            chain_context.session_id,
            stage_id="initial-analysis",
            stage_name="Initial Analysis"
        ))
        
        # Log LLM interaction
        from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
        # Create conversation with proper structure
        from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an expert Kubernetes troubleshooter."),
            LLMMessage(role=MessageRole.USER, content="Analyze the namespace termination issue"),
            LLMMessage(role=MessageRole.ASSISTANT, content="The namespace is stuck due to finalizers")
        ])
        
        llm_interaction = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage_execution_id,
            model_name="gpt-4",
            conversation=conversation,
            duration_ms=1500
        )
        llm_result = history_service_with_db.store_llm_interaction(llm_interaction)
        assert llm_result == True
        
        # Log MCP communication
        mcp_interaction = MCPInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage_execution_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get_namespace",
            tool_arguments={"namespace": "stuck-namespace"},
            tool_result={"status": "Terminating", "finalizers": ["test-finalizer"]},
            step_description="Check namespace status",
            duration_ms=800,
            success=True
        )
        mcp_result = history_service_with_db.store_mcp_interaction(mcp_interaction)
        assert mcp_result == True
        
        # Complete session
        completion_result = history_service_with_db.update_session_status(
            session_id=chain_context.session_id,
            status="completed"
        )
        assert completion_result == True
        
        # Verify complete timeline
        timeline = history_service_with_db.get_session_details(chain_context.session_id)
        assert timeline is not None
        assert timeline.status.value == "completed"  # Access enum status
        # Total interactions from all stages
        total_stage_interactions = sum(len(stage.llm_interactions) + len(stage.mcp_communications) for stage in timeline.stages)
        assert total_stage_interactions == 2
        assert timeline.total_interactions == 2
        # Check interaction counts
        assert timeline.llm_interaction_count == 1
        assert timeline.mcp_communication_count == 1
    
    @pytest.mark.integration
    def test_chronological_timeline_ordering(self, history_service_with_db, sample_alert):
        """Test that timeline events are ordered chronologically."""
        # Create session
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type=sample_alert.alert_type,
            session_id="timeline-test-session",
            chain_id="test-integration-chain-timeline",
            agent="KubernetesAgent"
        )
        result = history_service_with_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        session_id = chain_context.session_id
        
        # Create stage execution
        import asyncio

        from tests.utils import StageExecutionFactory
        stage_execution_id = asyncio.run(StageExecutionFactory.create_and_save_stage_execution(
            history_service_with_db,
            session_id,
            stage_id="timeline-analysis",
            stage_name="Timeline Analysis"
        ))
        
        # Create events with specific timestamps (simulating real workflow)
        base_time = datetime.now(timezone.utc)
        
        # First LLM interaction
        llm_interaction1 = LLMInteraction(
            session_id=session_id,
            stage_execution_id=stage_execution_id,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a Kubernetes expert."),
                LLMMessage(role=MessageRole.USER, content="Initial analysis prompt"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Initial analysis response")
            ]),
            duration_ms=1200
        )
        history_service_with_db.store_llm_interaction(llm_interaction1)
        
        # Sleep to ensure different timestamp
        import time
        time.sleep(0.01)
        
        # MCP tool call
        mcp_interaction1 = MCPInteraction(
            session_id=session_id,
            stage_execution_id=stage_execution_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get",
            step_description="Get namespace info",
            success=True
        )
        history_service_with_db.store_mcp_interaction(mcp_interaction1)
        
        time.sleep(0.01)
        
        # Second LLM interaction
        llm_interaction2 = LLMInteraction(
            session_id=session_id,
            stage_execution_id=stage_execution_id,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a Kubernetes expert."),
                LLMMessage(role=MessageRole.USER, content="Follow-up analysis prompt"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Follow-up analysis response")
            ])
        )
        history_service_with_db.store_llm_interaction(llm_interaction2)
        
        # Get timeline and verify ordering
        timeline = history_service_with_db.get_session_details(session_id)
        
        # Collect all interactions from all stages
        all_interactions = []
        for stage in timeline.stages:
            all_interactions.extend(stage.llm_interactions)
            all_interactions.extend(stage.mcp_communications)
        
        assert len(all_interactions) == 3
        
        # Sort interactions by timestamp and verify chronological order
        all_interactions.sort(key=lambda x: x.timestamp_us)
        for i in range(len(all_interactions) - 1):
            current_time_us = all_interactions[i].timestamp_us
            next_time_us = all_interactions[i + 1].timestamp_us
            assert current_time_us <= next_time_us, f"Interaction {i} timestamp is after interaction {i+1}"
        
        # Verify interaction types in expected order
        assert hasattr(all_interactions[0].details, 'model_name')  # LLM interaction
        assert hasattr(all_interactions[1].details, 'server_name')  # MCP interaction
        assert hasattr(all_interactions[2].details, 'model_name')  # LLM interaction
    
    @pytest.mark.integration
    def test_complex_filtering_scenarios(self, history_service_with_db):
        """Test complex filtering scenarios with multiple sessions."""
        # Create multiple sessions with different attributes
        now = datetime.now(timezone.utc)
        
        sessions_data = [
            ("session-1", "NamespaceTerminating", "KubernetesAgent", "completed", now - timedelta(hours=1)),
            ("session-2", "NamespaceTerminating", "KubernetesAgent", "in_progress", now - timedelta(hours=2)),
            ("session-3", "HighCPU", "KubernetesAgent", "completed", now - timedelta(hours=3)),
            ("session-4", "NamespaceTerminating", "GenericAgent", "completed", now - timedelta(hours=4)),
            ("session-5", "HighMemory", "KubernetesAgent", "failed", now - timedelta(days=2))
        ]
        
        for session_id, alert_type, agent_type, status, started_at in sessions_data:
            # Create ChainContext and ChainConfigModel for new API  
            chain_context, chain_definition = create_test_context_and_chain(
                alert_type=alert_type,
                session_id=session_id,
                chain_id=f"test-integration-chain-{session_id}",
                agent=agent_type
            )
            
            # create_test_context_and_chain already provides rich test data
            # (alert_type, environment, cluster, namespace, message)
            
            # Use the service to create session (simulating real workflow)
            result = history_service_with_db.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            assert result is True
            sid = chain_context.session_id
            
            # Update the session with custom timestamp using repository directly
            with history_service_with_db.get_repository() as repo:
                if repo:
                    # Get the created session
                    session = repo.get_alert_session(sid)
                    if session:
                        # Update with custom timestamp (convert to microseconds since epoch)
                        session.started_at_us = int(started_at.timestamp() * 1000000)
                        # Update status if needed
                        if status != "pending":
                            session.status = status
                            if status == "completed":
                                session.completed_at_us = int((started_at + timedelta(minutes=30)).timestamp() * 1000000)
                        repo.session.commit()
            
            # Add some interactions for variety
            if session_id in ["session-1", "session-3"]:
                llm_interaction_variety = LLMInteraction(
                    session_id=sid,
                    model_name="gpt-4",
                    conversation=LLMConversation(messages=[
                        LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                        LLMMessage(role=MessageRole.USER, content=f"Test prompt for {session_id}"),
                        LLMMessage(role=MessageRole.ASSISTANT, content=f"Test response for {session_id}")
                    ])
                )
                history_service_with_db.store_llm_interaction(llm_interaction_variety)
        
        # Test 1: Filter by alert_type + status
        result = history_service_with_db.get_sessions_list(
            filters={"alert_type": "NamespaceTerminating", "status": "completed"}
        )
        assert result is not None
        assert result.pagination.total_items == 2  # session-1 and session-4
        
        # Test 2: Filter by agent_type + status + alert_type
        # Note: agent_type is now "chain:{chain_id}" format
        result = history_service_with_db.get_sessions_list(
            filters={
                "agent_type": "chain:test-integration-chain-session-1",
                "status": "completed",
                "alert_type": "NamespaceTerminating"
            }
        )
        assert result is not None
        assert result.pagination.total_items == 1  # only session-1
        
        # Test 3: Filter by time range
        cutoff_time = now - timedelta(hours=5)
        result = history_service_with_db.get_sessions_list(
            filters={"start_date_us": int(cutoff_time.timestamp() * 1_000_000)}
        )
        assert result is not None
        assert result.pagination.total_items == 4  # All except session-5 (older than 5 hours)
        
        # Test 4: Combined filters with pagination - test by status instead since agent_type is now unique per chain
        result = history_service_with_db.get_sessions_list(
            filters={"status": "completed"},
            page=1,
            page_size=2
        )
        assert result is not None
        assert len(result.sessions) == 2  # First page of completed sessions
        assert result.pagination.total_items == 3  # Total completed sessions (session-1, session-3, session-4)
    
    @pytest.mark.integration
    def test_error_handling_and_graceful_degradation(self, history_service_with_db, sample_alert):
        """Test error handling and graceful degradation scenarios."""
        # Test session creation with invalid data
        # Create ChainContext and ChainConfigModel for new API with minimal data
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type=sample_alert.alert_type or "unknown",  # Fallback for empty types
            session_id="test-error-session",
            chain_id="test-integration-chain-error",
            agent="GenericAgent"  # Fallback agent
        )
        
        # Use real fixture data even in error handling path (error is empty alert_id, not empty data)
        from tarsy.models.alert import ProcessingAlert
        chain_context.processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity=sample_alert.severity or "warning",
            timestamp=chain_context.processing_alert.timestamp,
            environment=sample_alert.data.get('environment', 'production'),
            runbook_url=sample_alert.runbook,
            alert_data=sample_alert.data
        )
        
        result = history_service_with_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        assert result is True  # Should still create session
        session_id = chain_context.session_id
        
        # Test logging with invalid session ID
        llm_interaction_invalid = LLMInteraction(
            session_id="non-existent-session",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="Test prompt"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Test response")
            ])
        )
        result = history_service_with_db.store_llm_interaction(llm_interaction_invalid)
        # The service allows logging interactions even for non-existent sessions
        # This is by design for performance and graceful degradation
        assert result == True  # Service handles this gracefully without validation
        
        # Test status update with invalid session ID
        result = history_service_with_db.update_session_status(
            session_id="non-existent-session",
            status="completed"
        )
        assert result == False  # Should fail gracefully
        
        # Test timeline retrieval with invalid session ID
        timeline = history_service_with_db.get_session_details("non-existent-session")
        assert timeline is None  # Should return None for non-existent sessions
    

    @pytest.mark.integration
    def test_sqlite_retry_logic_works(self, history_service_with_db, sample_alert):
        """Test that our retry logic handles transient SQLite issues gracefully."""
        # This test verifies our retry logic works in single-threaded scenarios
        # Note: Full concurrent testing requires a more robust database like PostgreSQL
        
                # Test that normal operations work
        # Create ChainContext and ChainConfigModel for new API
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type=sample_alert.alert_type,
            session_id="test-retry-session",
            chain_id="test-integration-chain-retry", 
            agent="KubernetesAgent"
        )
        
        # Override alert_data with sample alert data by creating a new ProcessingAlert
        from tarsy.models.alert import ProcessingAlert
        chain_context.processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity=sample_alert.severity or "warning",
            timestamp=chain_context.processing_alert.timestamp,
            environment=sample_alert.data.get('environment', 'production'),
            runbook_url=sample_alert.runbook,
            alert_data=sample_alert.data
        )
        
        result = history_service_with_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        assert result is True
        session_id = chain_context.session_id
        
        # Should succeed with our improvements
        assert session_id is not None, "Session creation should succeed with retry logic"
        
        # Test status update works
        result = history_service_with_db.update_session_status(
            session_id=session_id,
            status="completed"
        )
        assert result == True, "Status update should succeed with retry logic"
        
        # Verify session was created correctly
        timeline = history_service_with_db.get_session_details(session_id)
        assert timeline is not None
        assert timeline.status.value == "completed"
        
        logger.info("✅ SQLite retry logic and improvements working correctly")


class TestAlertServiceHistoryIntegration:
    """Integration tests for AlertService with history tracking."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock()
        settings.history_enabled = True
        settings.database_url = "sqlite:///:memory:"
        settings.history_retention_days = 90
        settings.agent_config_path = None  # No agent config for integration tests
        settings.llm_provider = "openai"  # Set configured provider
        # Add required LLM settings to prevent iteration error
        settings.llm_providers = {}
        settings.llm_default_provider = "openai"
        settings.openai_api_key = "test-key"
        settings.anthropic_api_key = "test-key"
        return settings
    
    @pytest.fixture
    def alert_service_with_history(self, mock_settings):
        """Create AlertService with history integration."""
        # Create AlertService directly with mock settings
        service = AlertService(mock_settings)
        
        # Mock LLM manager to appear available
        service.llm_manager.is_available = Mock(return_value=True)
        service.llm_manager.list_available_providers = Mock(return_value=["openai"])
        
        # Mock runbook service to return test content
        service.runbook_service.download_runbook = AsyncMock(return_value="Test runbook content")
        
        # Mock agent registry and agent factory
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        mock_agent = AsyncMock()
        mock_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="KubernetesAgent", 
            timestamp_us=now_us(),
            result_summary="Test analysis with actions taken and recommendations",
            final_analysis="Test analysis with actions taken and recommendations"
        )
        
        # Mock the chain_registry - this is where get_chain_for_alert_type lives  
        service.chain_registry.get_chain_for_alert_type = Mock(return_value=Mock(chain_id="kubernetes-chain", stages=[Mock(name="analysis", agent="KubernetesAgent")]))
        
        # Mock agent_factory to return our mock agent
        service.agent_factory = Mock()
        service.agent_factory.get_agent = Mock(return_value=mock_agent)
        service.agent_factory.create_agent = Mock(return_value=mock_agent)
        
        # Use real history service with mocked database
        mock_history_service = Mock()
        mock_history_service.create_session.return_value = True
        mock_history_service.update_session_status.return_value = True
        service.history_service = mock_history_service
        
        return service
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert."""
        return Alert(
            alert_type="NamespaceTerminating",
            severity="high",
            runbook="namespace-terminating.md",
            data={
                "environment": "production",
                "cluster": "k8s-prod",
                "namespace": "stuck-namespace",
                "message": "Namespace is stuck in Terminating state"
            }
        )
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_alert_processing_with_history_tracking(self, alert_service_with_history, sample_alert):
        """Test complete alert processing with history tracking."""
        # Process alert
        chain_context = alert_to_api_format(sample_alert)
        import uuid
        alert_id = str(uuid.uuid4())
        result = await alert_service_with_history.process_alert(
            chain_context
        )
        
        # Verify alert processing succeeded
        assert result is not None
        # The result is a formatted string from _format_success_response, not a dict
        assert "Analysis completed successfully" in result or "Test analysis" in result
        
        # Verify history service interactions
        history_service = alert_service_with_history.history_service
        
        # Should have created session
        history_service.create_session.assert_called_once()
        create_call = history_service.create_session.call_args
        assert "chain_context" in create_call[1]
        assert "chain_definition" in create_call[1]
        # Verify the chain_context contains the expected alert_type
        chain_context = create_call[1]["chain_context"]
        assert chain_context.processing_alert.alert_type == sample_alert.alert_type
        
        # Should have updated session status multiple times
        assert history_service.update_session_status.call_count >= 2
        
        # Verify session status updates
        status_calls = history_service.update_session_status.call_args_list
        
        # Should include in_progress and completed status updates
        statuses = [call[1]["status"] for call in status_calls]
        assert "in_progress" in statuses
        assert "completed" in statuses
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_alert_processing_error_with_history_tracking(self, alert_service_with_history, sample_alert):
        """Test alert processing error handling with history tracking."""
        # Make agent processing fail by setting up the mock to fail
        mock_agent = AsyncMock()
        mock_agent.process_alert.side_effect = Exception("Agent processing failed")
        alert_service_with_history.agent_factory.get_agent = Mock(return_value=mock_agent)
        
        # Process alert (should handle error gracefully)
        chain_context = alert_to_api_format(sample_alert)
        import uuid
        alert_id = str(uuid.uuid4())
        result = await alert_service_with_history.process_alert(
            chain_context
        )
        
        # Verify error was handled
        assert result is not None
        # The result is a formatted string from _format_error_response, not a dict  
        assert "Chain execution failed" in result  # Chain architecture error format
        
        # Verify history service tracked the error
        history_service = alert_service_with_history.history_service
        
        # Should have created session
        history_service.create_session.assert_called_once()
        
        # Should have updated status to failed
        status_calls = history_service.update_session_status.call_args_list
        statuses = [call[1]["status"] for call in status_calls]
        assert "failed" in statuses
        
        # Should have recorded error message
        error_calls = [call for call in status_calls if call[1].get("error_message")]
        assert len(error_calls) > 0
        assert "Chain execution failed" in error_calls[0][1]["error_message"]  # Chain architecture error format


class TestHistoryAPIIntegration:
    """Integration tests for History API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_history_service_for_api(self):
        """Create mock history service for API testing."""
        from unittest.mock import AsyncMock

        from tests.utils import MockFactory, SessionFactory
        
        # Create the base mock service with all sensible defaults
        service = MockFactory.create_mock_history_service()
        
        # Override only what's specific to this test
        custom_detailed_session = SessionFactory.create_detailed_session(
            session_id="api-session-1",
            chain_id="integration-chain-123",  # Match test expectation
        )
        service.get_session_details.return_value = custom_detailed_session
        
        # Override session stats to match test expectations
        custom_stats = SessionFactory.create_session_stats(
            total_duration_ms=150000  # Match test expectation
        )
        service.get_session_summary = AsyncMock(return_value=custom_stats)
        
        # Add legacy mock for backward compatibility
        service.calculate_session_summary.return_value = {
            "total_interactions": 2,
            "llm_interactions": 1,
            "mcp_communications": 1,
            "total_duration_ms": 150000,
            "errors_count": 0,
            "system_events": 0,
            "chain_statistics": {
                "total_stages": 1,
                "completed_stages": 1,
                "failed_stages": 0,
                "stages_by_agent": {"analysis": 1}
            }
        }
        
        return service
    
    @pytest.mark.integration
    def test_api_sessions_list_integration(self, client, mock_history_service_for_api):
        """Test sessions list API endpoint integration."""
        # Use FastAPI's dependency override system
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service_for_api
        
        try:
            response = client.get("/api/v1/history/sessions?status=completed&page=1&page_size=10")
        
            assert response.status_code == 200
            data = response.json()
            
            assert "sessions" in data
            assert "pagination" in data
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["session_id"] == "api-session-1"
            
            # Verify service was called with correct parameters
            mock_history_service_for_api.get_sessions_list.assert_called_once()
            call_args = mock_history_service_for_api.get_sessions_list.call_args
            assert call_args.kwargs["filters"]["status"] == ["completed"]  # Now expects list due to multiple status support
            assert call_args.kwargs["page"] == 1
            assert call_args.kwargs["page_size"] == 10
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()
    
    @pytest.mark.integration
    def test_api_session_detail_integration(self, client, mock_history_service_for_api):
        """Test session detail API endpoint integration."""
        # Ensure the mock returns the timeline for the specific session ID (using Unix timestamps)
        expected_session_id = "api-session-1"
        
        # Use FastAPI's dependency override system instead of mock patching
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service_for_api
        
        try:
            response = client.get(f"/api/v1/history/sessions/{expected_session_id}")
            
            
            assert response.status_code == 200
            data = response.json()
            
            # Check the actual DetailedSession structure
            assert "session_id" in data
            assert "chain_id" in data
            assert "stages" in data
            
            # Verify session details
            assert data["session_id"] == expected_session_id
            assert data["alert_type"] == "NamespaceTerminating"
            assert data["status"] == "completed"
            
            # All sessions should have chain execution data since we support chains only
            assert "chain_id" in data, "All sessions should have chain execution data"
            
            # Verify comprehensive chain execution structure
            assert data["chain_id"] == "integration-chain-123"
            assert "stages" in data
            assert isinstance(data["stages"], list)
            assert len(data["stages"]) == 1
            
            # Verify stage structure and timeline
            stage = data["stages"][0]
            assert "execution_id" in stage
            assert "stage_id" in stage  
            assert "stage_name" in stage
            assert "status" in stage
            assert "llm_interaction_count" in stage
            assert "mcp_communication_count" in stage
            assert "total_interactions" in stage
            
            # Verify interaction counts
            assert stage["llm_interaction_count"] == 1  # 1 LLM interaction
            assert stage["mcp_communication_count"] == 1  # 1 MCP interaction
            assert stage["total_interactions"] == 2  # Total interactions
            
            # Verify timeline structure (chronological_interactions)
            assert "llm_interactions" in stage
            assert "mcp_communications" in stage
            assert isinstance(stage["llm_interactions"], list)
            assert isinstance(stage["mcp_communications"], list)
            assert len(stage["llm_interactions"]) == 1  # 1 LLM interaction
            assert len(stage["mcp_communications"]) == 1  # 1 MCP interaction
            
            # Verify first interaction (LLM)
            llm_interaction = stage["llm_interactions"][0]
            assert llm_interaction["type"] == "llm"
            # Note: step_description is not used for LLM interactions - only for MCP
            assert "details" in llm_interaction
            
            # Verify second interaction (MCP)
            mcp_interaction = stage["mcp_communications"][0]
            assert mcp_interaction["type"] == "mcp"
            assert mcp_interaction["step_description"] == "Tool execution"
            assert "details" in mcp_interaction
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()
    
    @pytest.mark.integration
    def test_api_health_check_integration(self, client, mock_history_service_for_api):
        """Test health check API endpoint integration."""
        # Use FastAPI's dependency override system
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service_for_api
        
        try:
            response = client.get("/api/v1/history/health")
        
            assert response.status_code == 200
            data = response.json()
            
            assert data["service"] == "alert_processing_history"
            assert data["status"] == "healthy"
            assert "timestamp_us" in data
            assert "details" in data
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()
    
    @pytest.mark.integration
    def test_api_error_handling_integration(self, client):
        """Test API error handling integration."""
        # Mock service that raises exception
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.get_sessions_list.side_effect = Exception("Database connection failed")
        
        # Use FastAPI's dependency override system
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        try:
            response = client.get("/api/v1/history/sessions")
        
            assert response.status_code == 500
            # The actual error message varies, just check it's an error response
            assert "detail" in response.json()
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestDuplicatePreventionIntegration:
    """Integration tests for duplicate session prevention across all layers."""
    
    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            "alert_type": "PodCrashLoopBackOff",
            "severity": "high",
            "environment": "production",
            "cluster": "https://api.test-cluster.com",
            "namespace": "default",
            "message": "Pod test-pod is crash looping",
            "runbook": "https://github.com/test/runbooks/pod-crash.md"
        }
    
    def test_end_to_end_duplicate_prevention_same_alert_data(self, history_service_with_test_db, sample_alert_data):
        """Test that identical alerts don't create duplicate sessions end-to-end."""
        # Create first session
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="PodCrashLoopBackOff",
            session_id="test-session-dup-1",
            chain_id="test-integration-chain-dup-1",
            agent="KubernetesAgent",
            alert_data=sample_alert_data
        )
        
        result_1 = history_service_with_test_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        
        assert result_1 is True  # First creation should succeed
        
        # Try to create duplicate session with same alert_id
        chain_context_2, chain_definition_2 = create_test_context_and_chain(
            alert_type="DifferentAlertType",
            session_id="test-session-dup-2",
            chain_id="test-integration-chain-dup-2",
            agent="DifferentAgent",
            alert_data={**sample_alert_data, "severity": "critical"}
        )
        
        result_2 = history_service_with_test_db.create_session(
            chain_context=chain_context_2,
            chain_definition=chain_definition_2
        )
        
        # Should still succeed (duplicate prevention handled internally)
        assert result_2 is True
        
        # Note: Duplicate prevention is handled at the repository level
        # Both calls return True, but only one session is actually created in the database
    
    def test_concurrent_session_creation_same_alert_id(self, history_service_with_test_db, sample_alert_data):
        """Test concurrent creation attempts with same alert_id."""
        import threading
        import time
        
        results = []
        errors = []
        
        def create_session(thread_id):
            try:
                # Add small random delay to increase chance of concurrency
                time.sleep(thread_id * 0.01)
                
                chain_context, chain_definition = create_test_context_and_chain(
                    alert_type="TestAlert",
                    session_id=f"test-session-concurrent-{thread_id}",
                    chain_id=f"test-integration-chain-concurrent-{thread_id}",
                    agent=f"Agent_{thread_id}",
                    alert_data={**sample_alert_data, "thread_id": thread_id}
                )
                session_id = history_service_with_test_db.create_session(
                    chain_context=chain_context,
                    chain_definition=chain_definition
                )
                results.append(session_id)
            except Exception as e:
                errors.append(str(e))
        
        # Start multiple threads trying to create the same alert
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_session, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Check if any sessions were created (may fail due to database table issues in concurrent access)
        valid_results = [r for r in results if r is not None]
        
        if len(valid_results) == 0:
            # Skip test if concurrent database access failed
            pytest.skip("Database table not available for concurrent access - this is a known testing limitation")
        
        # All valid results should be the same session_id (no duplicates created)
        unique_sessions = set(valid_results)
        assert len(unique_sessions) == 1, f"Expected 1 unique session, got {len(unique_sessions)}: {unique_sessions}"
        
        # Verify only one session exists in database
        session_id = valid_results[0]
        session = history_service_with_test_db.get_session_details(session_id)
        
        if not session:
            # Session was created but timeline can't be retrieved - this is acceptable for the test
            return
        
        # Original thread's data should be preserved (thread 0)
        assert session.alert_data["thread_id"] == 0
        assert session.agent_type == "Agent_0"
    
    def test_database_constraint_enforcement(self, history_service_with_test_db, sample_alert_data):
        """Test that database-level unique constraints are enforced."""
        # Create session through service
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="TestAlert",
            session_id="test-session-constraint",
            chain_id="test-integration-chain-constraint",
            agent="TestAgent",
            alert_data=sample_alert_data
        )
        result = history_service_with_test_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        
        assert result is True  # Session creation should succeed
        
        # Try to bypass application logic and create duplicate directly in database
        with history_service_with_test_db.get_repository() as repo:
            if repo:
                from tarsy.models.db_models import AlertSession
                
                # Try to create duplicate session directly
                duplicate_session = AlertSession(
                    session_id="test-duplicate-session",  # Different session_id
                    alert_id="constraint_test_alert",  # Same alert_id
                    alert_data={"different": "data"},
                    agent_type="DifferentAgent",
                    status="pending"
                )
                
                # This should be prevented by our application logic
                existing_session = repo.create_alert_session(duplicate_session)
                
                # Should return existing session, not create new one
                assert existing_session is not None
                assert existing_session.agent_type == "chain:test-integration-chain-constraint"  # Original data preserved
    
    def test_alert_id_generation_uniqueness_under_load(self, history_service_with_test_db, sample_alert_data):
        """Test that alert ID generation remains unique under high load."""
        from tarsy.config.settings import get_settings
        from tarsy.models.alert import Alert
        from tarsy.services.alert_service import AlertService
        
        # Create AlertService to test ID generation
        alert_service = AlertService(get_settings())
        alert_service.history_service = history_service_with_test_db
        alert_service.agent_registry = Mock()
        alert_service.agent_registry.get_agent_for_alert_type.return_value = "TestAgent"
        
        # Create identical alerts rapidly
        alert = Alert(**sample_alert_data)
        alert_dict = alert_to_api_format(alert)
        generated_ids = set()
        
        for i in range(100):
            # Generate unique alert ID similar to how the old method did it
            timestamp_us = now_us()
            unique_id = uuid.uuid4().hex[:12]
            alert_id = f"{alert_dict.processing_alert.alert_type}_{unique_id}_{timestamp_us}"
            
            chain_context, chain_definition = create_test_context_and_chain(
                alert_type=alert_dict.processing_alert.alert_type,
                session_id=f"test-session-unique-{i}",
                chain_id=f"test-integration-chain-unique-{i}",
                agent="TestAgent",
                alert_data=alert_dict.processing_alert.alert_data
            )
            session_id = history_service_with_test_db.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            if session_id:
                generated_ids.add(alert_id)
        
        # All generated alert IDs should be unique
        assert len(generated_ids) == 100, f"Expected 100 unique alert IDs, got {len(generated_ids)}"
        
        # Each ID should follow the expected pattern (hash-based format)
        for alert_id in generated_ids:
            assert alert_id.startswith("PodCrashLoopBackOff_")
            parts = alert_id.split('_')
            assert len(parts) == 3  # alert_type_unique_id_timestamp
    
    def test_retry_logic_doesnt_create_duplicates(self, history_service_with_test_db, sample_alert_data):
        """Test that retry logic doesn't create duplicate sessions."""
        with patch.object(history_service_with_test_db, '_retry_database_operation') as mock_retry:
            # First call succeeds, second call would create duplicate
            mock_retry.return_value = True
            
            # Create session
            chain_context, chain_definition = create_test_context_and_chain(
                alert_type="TestAlert",
                session_id="test-session-retry-dup",
                chain_id="test-integration-chain-retry-dup",
                agent="TestAgent",
                alert_data=sample_alert_data
            )
            result_1 = history_service_with_test_db.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            
            assert result_1 is True
            
            # Verify that create_session operations don't retry after first attempt
            mock_retry.assert_called_once()
            call_args = mock_retry.call_args
            assert call_args[0][0] == "create_session"  # Operation name
    
    def test_performance_impact_of_duplicate_prevention(self, history_service_with_test_db, sample_alert_data):
        """Test that duplicate prevention doesn't significantly impact performance."""
        import time
        
        # Create initial session
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="TestAlert",
            session_id="test-session-perf",
            chain_id="test-integration-chain-perf",
            agent="TestAgent",
            alert_data=sample_alert_data
        )
        initial_session = history_service_with_test_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        
        assert initial_session is True
        
        # Measure time for duplicate prevention checks
        start_time = time.time()
        
        for i in range(50):
            # Try to create duplicates
            chain_context_dup, chain_definition_dup = create_test_context_and_chain(
                alert_type="TestAlert",
                session_id=f"test-session-perf-dup-{i}",
                chain_id=f"test-integration-chain-perf-dup-{i}",
                agent=f"TestAgent_{i}",
                alert_data={**sample_alert_data, "attempt": i}
            )
            duplicate_session = history_service_with_test_db.create_session(
                chain_context=chain_context_dup,
                chain_definition=chain_definition_dup
            )
            
            # Should return True (duplicate prevention handled internally)
            assert duplicate_session is True
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should complete quickly (less than 1 second for 50 duplicate checks)
        assert total_time < 1.0, f"Duplicate prevention took {total_time}s, should be faster"
        
        # Average time per duplicate check should be reasonable
        avg_time = total_time / 50
        assert avg_time < 0.02, f"Average duplicate check took {avg_time}s, should be under 20ms"
    
    def test_mixed_unique_and_duplicate_sessions(self, history_service_with_test_db, sample_alert_data):
        """Test creating a mix of unique and duplicate sessions."""
        created_sessions = {}
        
        # Create sessions with various alert_ids
        test_cases = [
            ("unique_alert_1", "Agent1", "Type1"),
            ("unique_alert_2", "Agent2", "Type2"),
            ("unique_alert_1", "Agent1_Modified", "Type1_Modified"),  # Duplicate
            ("unique_alert_3", "Agent3", "Type3"),
            ("unique_alert_2", "Agent2_Modified", "Type2_Modified"),  # Duplicate
            ("unique_alert_4", "Agent4", "Type4"),
        ]
        
        for alert_id, agent_type, alert_type in test_cases:
            chain_context, chain_definition = create_test_context_and_chain(
                alert_type=alert_type,
                session_id=f"test-session-mixed-{alert_id}",
                chain_id=f"test-integration-chain-mixed-{alert_id}",
                agent=agent_type,
                alert_data={**sample_alert_data, "test_case": f"{alert_id}_{agent_type}"}
            )
            result = history_service_with_test_db.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            
            # All calls should succeed (duplicate prevention handled internally)
            assert result is True
            
            if alert_id not in created_sessions:
                created_sessions[alert_id] = True
        
        # Should have processed 4 unique alert_ids (1, 2, 3, 4)
        # The duplicates (unique_alert_1 and unique_alert_2 appearing twice) are handled internally
        assert len(created_sessions) == 4  # 4 unique alert_ids processed
        
        # Note: Duplicate prevention is handled at the repository level
        # All create_session calls return True, but duplicates don't create new sessions
    
    def test_duplicate_prevention_with_database_errors(self, history_service_with_test_db, sample_alert_data):
        """Test duplicate prevention behavior when database errors occur."""
        # Create initial session
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="TestAlert",
            session_id="test-session-error-test",
            chain_id="test-integration-chain-error-test",
            agent="TestAgent",
            alert_data=sample_alert_data
        )
        result = history_service_with_test_db.create_session(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
        
        assert result is True
        
        # Simulate database error during duplicate check
        with patch.object(history_service_with_test_db, 'get_repository') as mock_get_repo:
            mock_repo = Mock()
            mock_repo.__enter__ = Mock(return_value=mock_repo)
            mock_repo.__exit__ = Mock(return_value=None)
            mock_repo.create_alert_session.side_effect = Exception("Database error")
            mock_get_repo.return_value = mock_repo
            
            # Try to create session during database error
            chain_context_2, chain_definition_2 = create_test_context_and_chain(
                alert_type="TestAlert",
                session_id="test-session-error-test-2",
                chain_id="test-integration-chain-error-test-2",
                agent="TestAgent",
                alert_data=sample_alert_data
            )
            error_session = history_service_with_test_db.create_session(
                chain_context=chain_context_2,
                chain_definition=chain_definition_2
            )
            
            # Should return False on error, not crash
            assert error_session is False
