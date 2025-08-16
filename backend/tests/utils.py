"""
Test utilities for reducing redundancy and improving test maintainability.

This module provides shared utilities, factories, and helpers for tests.

FACTORY SYSTEM OVERVIEW
======================

This module contains 12 specialized factory classes for creating consistent test data:

1. AlertFactory - Alert objects and processing data
2. SessionFactory - Session data for history tests  
3. ChainFactory - Chain configurations for registry tests
4. AgentFactory - Agent mappings for registry tests
5. MockFactory - Common mock objects and dependencies
6. MCPServerFactory - MCP server configurations
7. DashboardFactory - Dashboard interaction data
8. AgentFactoryFactory - Agent factory test dependencies
9. RunbookFactory - Runbook service test data
10. DataMaskingFactory - Data masking service test data
11. DashboardConnectionFactory - WebSocket and connection test data
12. MCPServerMaskingFactory - MCP server masking and template configurations

WHEN TO USE FACTORIES
====================

Use factories when:
- You have complex test data that appears in multiple places
- There are repetitive setup patterns that could be centralized
- You need consistent test data across different test scenarios
- The test data has multiple variations that benefit from factory methods

Don't use factories for:
- Simple, one-off test data used in only one place
- Test data that's already well-structured with existing fixtures
- Cases where manual creation is clearer than factory usage

USAGE PATTERNS
=============

Basic usage:
    from tests.utils import AlertFactory, SessionFactory
    
    # Create with defaults
    alert = AlertFactory.create_kubernetes_alert()
    
    # Override specific fields
    alert = AlertFactory.create_kubernetes_alert(
        severity="warning",
        environment="staging"
    )

Parameterized tests:
    @pytest.mark.parametrize("alert_factory,expected_type", [
        (AlertFactory.create_kubernetes_alert, "kubernetes"),
        (AlertFactory.create_generic_alert, "generic"),
    ])
    def test_alert_processing(self, alert_factory, expected_type):
        alert = alert_factory()
        assert alert.alert_type == expected_type

Best practices:
- Use factories for consistency across tests
- Override only the fields you need to customize
- Choose the most appropriate factory method for your test context
- Keep factory methods focused and single-purpose
"""

import asyncio
from typing import Any, Dict, List, Optional, Union
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import WebSocket
from pydantic import ValidationError

from tarsy.models.alert import Alert
from tarsy.models.alert_processing import AlertProcessingData
from tarsy.utils.timestamp import now_us


class TestUtils:
    """Utility class for common test operations."""
    
    @staticmethod
    def assert_response_structure(response, expected_fields: List[str]):
        """Assert response has expected structure."""
        data = response.json()
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
    
    @staticmethod
    def create_mock_websocket():
        """Create a mock WebSocket for testing."""
        websocket = AsyncMock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.accept = AsyncMock()  # Added for dashboard connection compatibility
        return websocket
    
    @staticmethod
    def assert_validation_error(model_class, invalid_data: Dict[str, Any], expected_errors: List[str]):
        """Assert that model validation fails with expected errors."""
        with pytest.raises(ValidationError) as exc_info:
            model_class(**invalid_data)
        
        errors = exc_info.value.errors()
        error_messages = [error["msg"] for error in errors]
        
        for expected_error in expected_errors:
            assert any(expected_error in msg for msg in error_messages), \
                f"Expected error '{expected_error}' not found in {error_messages}"
    
    @staticmethod
    def assert_model_serialization(model_instance, expected_fields: List[str]):
        """Assert model can be serialized and contains expected fields."""
        model_dict = model_instance.dict()
        for field in expected_fields:
            assert field in model_dict, f"Missing field in serialization: {field}"


class AlertFactory:
    """
    Factory for creating test Alert instances.
    
    Use when: You need Alert objects or AlertProcessingData for tests
    
    Examples:
        # Create a basic Kubernetes alert
        alert = AlertFactory.create_kubernetes_alert()
        
        # Override specific fields
        alert = AlertFactory.create_kubernetes_alert(
            severity="warning",
            environment="staging"
        )
        
        # Create alert processing data
        processing_data = AlertFactory.create_alert_processing_data()
        
        # Create custom alert
        custom_alert = AlertFactory.create_generic_alert(
            alert_type="custom",
            data={"custom_field": "value"}
        )
    
    Best practices:
        - Use factories for consistency across tests
        - Override only the fields you need to customize
        - Choose the most appropriate factory method for your test context
    """
    
    @staticmethod
    def create_kubernetes_alert(**overrides) -> Alert:
        """
        Create a Kubernetes alert with sensible defaults.
        
        Args:
            **overrides: Override any default values
            
        Returns:
            Alert: Configured Kubernetes alert
            
        Example:
            alert = AlertFactory.create_kubernetes_alert(severity="warning")
        """
        base_data = {
            "alert_type": "kubernetes",
            "runbook": "https://github.com/company/runbooks/blob/main/k8s.md",
            "severity": "critical",
            "timestamp": now_us(),
            "data": {
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "default",
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        }
        base_data.update(overrides)
        return Alert(**base_data)
    
    @staticmethod
    def create_generic_alert(**overrides) -> Alert:
        """Create a generic alert with sensible defaults."""
        base_data = {
            "alert_type": "generic",
            "runbook": "https://example.com/runbook",
            "severity": "warning",
            "timestamp": now_us(),
            "data": {
                "environment": "production",
                "message": "Generic alert message",
                "source": "monitoring-system"
            }
        }
        base_data.update(overrides)
        return Alert(**base_data)
    
    @staticmethod
    def create_minimal_alert(**overrides) -> Alert:
        """Create a minimal alert with only required fields."""
        base_data = {
            "alert_type": "test",
            "runbook": "https://example.com/minimal-runbook",
            "data": {}
        }
        base_data.update(overrides)
        return Alert(**base_data)


# AlertProcessingDataFactory removed - use AlertFactory instead for better consistency


class SessionFactory:
    """
    Factory for creating test session data.
    
    Use when: You need AlertSession instances for history-related tests
    
    Examples:
        # Create a basic test session
        session = SessionFactory.create_test_session()
        
        # Create sessions with different statuses
        pending_session = SessionFactory.create_pending_session()
        completed_session = SessionFactory.create_completed_session()
        failed_session = SessionFactory.create_failed_session()
        
        # Create session with custom data
        custom_session = SessionFactory.create_test_session(
            alert_type="custom",
            status=AlertSessionStatus.IN_PROGRESS
        )
    
    Best practices:
        - Use appropriate status-specific methods for clarity
        - Override only fields needed for your specific test scenario
        - Prefer factory methods over manual AlertSession construction
    """
    
    @staticmethod
    def create_test_session(**overrides):
        """Create a test session with sensible defaults."""
        from tarsy.models.history import AlertSession
        from tarsy.models.constants import AlertSessionStatus
        
        base_data = {
            "session_id": "test-session-123",
            "alert_id": "test-alert-456",
            "alert_data": {"alert_type": "kubernetes", "environment": "production"},
            "agent_type": "KubernetesAgent",
            "alert_type": "kubernetes",
            "status": AlertSessionStatus.PENDING.value,
            "started_at_us": 1640995200000000,  # 2022-01-01T00:00:00Z
            "completed_at_us": None,
            "error_message": None,
            "final_analysis": None,
            "chain_id": "test-chain-123"
        }
        base_data.update(overrides)
        return AlertSession(**base_data)
    
    @staticmethod
    def create_completed_session(**overrides):
        """Create a completed test session."""
        return SessionFactory.create_test_session(
            status="completed",
            completed_at_us=1640995260000000,  # 2022-01-01T00:01:00Z
            final_analysis="# Alert Analysis\n\nSuccessfully resolved the Kubernetes issue.",
            **overrides
        )
    
    @staticmethod
    def create_failed_session(**overrides):
        """Create a failed test session."""
        return SessionFactory.create_test_session(
            status="failed",
            completed_at_us=1640995260000000,
            error_message="Failed to process alert",
            **overrides
        )
    
    @staticmethod
    def create_in_progress_session(**overrides):
        """Create an in-progress test session."""
        return SessionFactory.create_test_session(
            status="in_progress",
            **overrides
        )


class StageExecutionFactory:
    """
    Factory for creating test stage execution data.
    
    Use when: You need stage executions for chain processing and timeline tests
    
    Examples:
        # Create basic stage execution
        stage_execution = StageExecutionFactory.create_test_stage_execution(
            session_id="test-session-123"
        )
        
        # Create stage execution with custom properties
        custom_stage = StageExecutionFactory.create_test_stage_execution(
            session_id="test-session-456",
            stage_id="custom-analysis",
            stage_name="Custom Analysis",
            agent="CustomAgent"
        )
        
        # Create completed stage execution
        completed_stage = StageExecutionFactory.create_completed_stage_execution(
            session_id="test-session-789"
        )
        
        # Create failed stage execution
        failed_stage = StageExecutionFactory.create_failed_stage_execution(
            session_id="test-session-101"
        )
    
    Best practices:
        - Always provide session_id to link to parent session
        - Use specific stage types when they match your test scenario
        - Override only the fields you need to customize
        - Use create_and_save_stage_execution for integration tests
    """
    
    @staticmethod
    def create_test_stage_execution(session_id: str, **overrides):
        """Create a basic test stage execution."""
        from tarsy.models.history import StageExecution
        from tarsy.models.constants import StageStatus
        
        base_data = {
            "session_id": session_id,
            "stage_id": "test-analysis",
            "stage_index": 0,
            "stage_name": "Test Analysis",
            "agent": "KubernetesAgent",
            "status": StageStatus.ACTIVE.value
        }
        base_data.update(overrides)
        return StageExecution(**base_data)
    
    @staticmethod
    def create_completed_stage_execution(session_id: str, **overrides):
        """Create a completed test stage execution."""
        from tarsy.models.constants import StageStatus
        import time
        
        now_ms = int(time.time() * 1000000)  # microseconds
        return StageExecutionFactory.create_test_stage_execution(
            session_id=session_id,
            status=StageStatus.COMPLETED.value,
            started_at_us=now_ms - 5000000,  # 5 seconds ago
            completed_at_us=now_ms,
            duration_ms=5000,
            stage_output={"analysis": "Stage completed successfully"},
            **overrides
        )
    
    @staticmethod
    def create_failed_stage_execution(session_id: str, **overrides):
        """Create a failed test stage execution."""
        from tarsy.models.constants import StageStatus
        import time
        
        now_ms = int(time.time() * 1000000)  # microseconds
        return StageExecutionFactory.create_test_stage_execution(
            session_id=session_id,
            status=StageStatus.FAILED.value,
            started_at_us=now_ms - 2000000,  # 2 seconds ago
            completed_at_us=now_ms,
            duration_ms=2000,
            error_message="Stage execution failed during processing",
            **overrides
        )
    
    @staticmethod
    async def create_and_save_stage_execution(history_service, session_id: str, **overrides):
        """
        Create and save a stage execution using the history service.
        
        Use this in integration tests where you need the stage execution 
        to be persisted to the database.
        
        Args:
            history_service: The history service instance
            session_id: Session ID to link to
            **overrides: Any field overrides
            
        Returns:
            str: The execution_id of the created stage execution
        """
        stage_execution = StageExecutionFactory.create_test_stage_execution(
            session_id=session_id, 
            **overrides
        )
        execution_id = await history_service.create_stage_execution(stage_execution)
        return execution_id


class ChainFactory:
    """
    Factory for creating test chain data.
    
    Use when: You need chain definitions for chain registry tests
    
    Examples:
        # Create standard chain configurations
        kubernetes_chain = ChainFactory.create_kubernetes_chain()
        simple_chain = ChainFactory.create_simple_chain()
        
        # Create custom chain
        custom_chain = ChainFactory.create_custom_chain(
            chain_id="my-chain",
            alert_types=["MyAlertType"],
            stages=[{"name": "analysis", "agent_class": "MyAgent"}]
        )
        
        # Create invalid chain for testing error handling
        invalid_chain = ChainFactory.create_invalid_chain()
    
    Best practices:
        - Use specific chain types (kubernetes, simple) when they match your test
        - Use create_custom_chain for specialized test scenarios
        - Override only the fields you need to customize
    """
    
    @staticmethod
    def create_kubernetes_chain(**overrides):
        """Create a Kubernetes chain with sensible defaults."""
        base_data = {
            "chain_id": "kubernetes-chain",
            "alert_types": ["kubernetes", "NamespaceTerminating"],
            "stages": [
                {
                    "name": "data-collection",
                    "agent": "KubernetesAgent",
                    "iteration_strategy": "regular"
                },
                {
                    "name": "analysis",
                    "agent": "KubernetesAgent",
                    "iteration_strategy": "react"
                }
            ],
            "description": "Kubernetes troubleshooting chain"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_simple_chain(**overrides):
        """Create a simple single-stage chain."""
        base_data = {
            "chain_id": "simple-chain",
            "alert_types": ["simple"],
            "stages": [
                {
                    "name": "analysis",
                    "agent": "SimpleAgent"
                }
            ],
            "description": "Simple analysis chain"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_custom_chain(**overrides):
        """Create a custom chain for testing."""
        base_data = {
            "chain_id": "custom-chain",
            "alert_types": ["custom"],
            "stages": [
                {
                    "name": "stage1",
                    "agent": "CustomAgent"
                }
            ],
            "description": "Custom chain for testing"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_invalid_chain(**overrides):
        """Create an invalid chain for testing error handling."""
        base_data = {
            "chain_id": "invalid-chain",
            "alert_types": ["invalid"],
            "stages": [
                {
                    "invalid": "missing required fields"  # Missing 'name' and 'agent'
                }
            ],
            "description": "Invalid chain for testing"
        }
        base_data.update(overrides)
        return base_data


class MockFactory:
    """
    Factory for creating common mock objects.
    
    Use when: You need standard mock dependencies for services
    
    Examples:
        # Create mock settings
        settings = MockFactory.create_mock_settings(github_token="test_token")
        
        # Create mock alert service dependencies
        deps = MockFactory.create_mock_alert_service_dependencies()
        
        # Create mock database manager
        db_manager = MockFactory.create_mock_database_manager()
    
    Best practices:
        - Use for consistent mock creation across tests
        - Prefer specific factory methods over generic Mock() creation
        - Override only the behavior you need for your specific test
    """
    
    @staticmethod
    def create_mock_settings(**overrides):
        """Create mock settings with sensible defaults."""
        mock_settings = Mock()
        default_settings = {
            "github_token": "test_token",
            "history_enabled": True,
            "agent_config_path": None,
            "log_level": "INFO",
            "max_concurrent_alerts": 5,
            "cors_origins": ["*"],
            "host": "localhost",
            "port": 8000,
            "gemini_api_key": "test-gemini-key",
            "openai_api_key": "test-openai-key",
            "grok_api_key": "test-grok-key",
            "default_llm_provider": "gemini",
            "max_llm_mcp_iterations": 3,
            "llm_providers": {
                "gemini": {
                    "model": "gemini-2.5-pro",
                    "api_key_env": "GEMINI_API_KEY",
                    "type": "gemini"
                },
                "openai": {
                    "model": "gpt-4-1106-preview",
                    "api_key_env": "OPENAI_API_KEY",
                    "type": "openai"
                },
                "grok": {
                    "model": "grok-3",
                    "api_key_env": "GROK_API_KEY",
                    "type": "grok"
                }
            }
        }
        
        for key, value in default_settings.items():
            setattr(mock_settings, key, value)
        
        for key, value in overrides.items():
            setattr(mock_settings, key, value)
        
        # Mock the get_llm_config method
        def mock_get_llm_config(provider: str):
            if provider not in mock_settings.llm_providers:
                raise ValueError(f"Unsupported LLM provider: {provider}")
            config = mock_settings.llm_providers[provider].copy()
            if provider == "gemini":
                config["api_key"] = mock_settings.gemini_api_key
            elif provider == "openai":
                config["api_key"] = mock_settings.openai_api_key
            elif provider == "grok":
                config["api_key"] = mock_settings.grok_api_key
            return config
        
        mock_settings.get_llm_config = mock_get_llm_config
        return mock_settings
    
    @staticmethod
    def create_mock_alert_service_dependencies():
        """Create mock dependencies for AlertService."""
        from unittest.mock import AsyncMock, Mock
        
        # Create mock objects directly
        mock_runbook = Mock()
        mock_history = Mock()
        mock_chain_registry = Mock()
        mock_mcp_registry = Mock()
        mock_mcp_client = Mock()
        mock_llm_manager = Mock()
        
        # Set up async methods
        mock_mcp_client.initialize = AsyncMock()
        mock_mcp_client.close = AsyncMock()
        mock_llm_manager.is_available.return_value = True
        
        return {
            'runbook': mock_runbook,
            'history': mock_history,
            'chain_registry': mock_chain_registry,
            'mcp_registry': mock_mcp_registry,
            'mcp_client': mock_mcp_client,
            'llm_manager': mock_llm_manager
        }
    
    @staticmethod
    def create_mock_history_service_dependencies():
        """Create mock dependencies for HistoryService - Phase 3: Updated for type-safe models."""
        from unittest.mock import Mock
        from tarsy.models.history_models import PaginatedSessions, FilterOptions, PaginationInfo, TimeRangeOption
        
        # Create mock objects
        mock_db_manager = Mock()
        mock_repository = Mock()
        mock_session = Mock()
        
        # Set up database manager
        mock_db_manager.create_tables.return_value = True
        mock_db_manager.get_session.return_value.__enter__ = Mock()
        mock_db_manager.get_session.return_value.__exit__ = Mock()
        
        # Set up repository - Phase 3: Repository methods now return type-safe models
        mock_session.session_id = "test-session-id"
        mock_repository.create_alert_session.return_value = mock_session
        mock_repository.get_alert_session.return_value = Mock()
        mock_repository.update_alert_session.return_value = True
        
        # get_alert_sessions now returns PaginatedSessions model
        mock_repository.get_alert_sessions.return_value = PaginatedSessions(
            sessions=[],  # Empty list of SessionOverview objects
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        
        # get_filter_options now returns FilterOptions model
        mock_repository.get_filter_options.return_value = FilterOptions(
            agent_types=["kubernetes", "network"],
            alert_types=["PodCrashLooping"],
            status_options=["pending", "in_progress", "completed", "failed"],
            time_ranges=[
                TimeRangeOption(label="Last Hour", value="1h"),
                TimeRangeOption(label="Today", value="today")
            ]
        )
        
        # Add mocks for other repository methods that may be called
        mock_repository.get_session_timeline.return_value = None
        mock_repository.get_session_with_stages.return_value = None
        
        return {
            'db_manager': mock_db_manager,
            'repository': mock_repository,
            'session': mock_session
        }
    
    @staticmethod
    def create_mock_detailed_session(session_id="test-session", **overrides):
        """
        Create a mock DetailedSession with sensible defaults for testing.
        
        Args:
            session_id: Session identifier (default: "test-session")
            **overrides: Override any default values
            
        Returns:
            DetailedSession: Configured DetailedSession for testing
            
        Example:
            session = MockFactory.create_mock_detailed_session(
                session_id="custom-session",
                llm_interaction_count=5,
                stages=[]
            )
        """
        from tarsy.models.history_models import DetailedSession, DetailedStage
        from tarsy.models.constants import AlertSessionStatus, StageStatus
        from tarsy.utils.timestamp import now_us
        
        base_data = {
            "session_id": session_id,
            "alert_id": f"alert-{session_id}",
            "alert_type": "TestAlert",
            "agent_type": "TestAgent",
            "status": AlertSessionStatus.COMPLETED,
            "started_at_us": now_us(),
            "completed_at_us": now_us() + 1000000,
            "error_message": None,
            "alert_data": {},
            "final_analysis": None,
            "session_metadata": None,
            "chain_id": f"chain-{session_id}",
            "chain_definition": {},
            "current_stage_index": None,
            "current_stage_id": None,
            "total_interactions": 1,
            "llm_interaction_count": 1,
            "mcp_communication_count": 0,
            "stages": [
                DetailedStage(
                    execution_id=f"stage-{session_id}",
                    session_id=session_id,
                    stage_id="stage-1",
                    stage_index=0,
                    stage_name="Test Stage",
                    agent="TestAgent",
                    status=StageStatus.COMPLETED,
                    started_at_us=now_us(),
                    completed_at_us=now_us() + 500000,
                    duration_ms=500,
                    stage_output=None,
                    error_message=None,
                    llm_interactions=[],
                    mcp_communications=[],
                    llm_interaction_count=1,
                    mcp_communication_count=0,
                    total_interactions=1
                )
            ]
        }
        base_data.update(overrides)
        return DetailedSession(**base_data)
    
    @staticmethod
    def create_mock_paginated_sessions(sessions=None, page=1, page_size=20, total_items=None, **overrides):
        """
        Create a mock PaginatedSessions with proper pagination.
        
        Args:
            sessions: List of SessionOverview objects (default: empty list)
            page: Page number (default: 1)
            page_size: Items per page (default: 20)
            total_items: Total items count (default: len(sessions))
            **overrides: Override any default values
            
        Returns:
            PaginatedSessions: Configured PaginatedSessions for testing
            
        Example:
            paginated = MockFactory.create_mock_paginated_sessions(
                sessions=session_overviews,
                total_items=10
            )
        """
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        
        if sessions is None:
            sessions = []
        if total_items is None:
            total_items = len(sessions)
        
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
        
        base_data = {
            "sessions": sessions,
            "pagination": PaginationInfo(
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                total_items=total_items
            ),
            "filters_applied": {}
        }
        base_data.update(overrides)
        return PaginatedSessions(**base_data)
    
    @staticmethod
    def create_mock_session_overviews(count=3):
        """
        Create a list of SessionOverview models for testing.
        
        Args:
            count: Number of SessionOverview objects to create (default: 3)
            
        Returns:
            List[SessionOverview]: List of configured SessionOverview objects
            
        Example:
            overviews = MockFactory.create_mock_session_overviews(count=5)
        """
        from tarsy.models.converters.session_converters import alert_session_to_session_overview
        
        # Use existing SessionFactory to create AlertSession objects, then convert
        alert_sessions = [SessionFactory.create_test_session() for _ in range(count)]
        return [alert_session_to_session_overview(session) for session in alert_sessions]


class ModelValidationTester:
    """Utility for testing model validation patterns."""
    
    @staticmethod
    def test_required_fields(model_class, required_fields: List[str], valid_data: Dict[str, Any]):
        """Test that required fields are enforced."""
        for field in required_fields:
            invalid_data = valid_data.copy()
            del invalid_data[field]
            # Dataclasses raise TypeError, Pydantic models raise ValidationError
            with pytest.raises((ValidationError, TypeError)):
                model_class(**invalid_data)
    
    @staticmethod
    def test_field_types(model_class, field_type_tests: Dict[str, List[Any]]):
        """Test field type validation."""
        for field, invalid_values in field_type_tests.items():
            for invalid_value in invalid_values:
                with pytest.raises(ValidationError):
                    model_class(**{field: invalid_value})
    
    @staticmethod
    def test_enum_values(model_class, enum_field: str, valid_values: List[str], invalid_values: List[str]):
        """Test enum field validation."""
        # Test valid values
        for valid_value in valid_values:
            try:
                model_class(**{enum_field: valid_value})
            except ValidationError:
                pytest.fail(f"Valid enum value '{valid_value}' was rejected")
        
        # Test invalid values
        for invalid_value in invalid_values:
            with pytest.raises(ValidationError):
                model_class(**{enum_field: invalid_value})


# AsyncTestUtils removed - simple async testing doesn't need a specialized factory


class AgentFactory:
    """Factory for creating test agent configurations."""
    
    @staticmethod
    def create_default_mappings():
        """Create default agent mappings."""
        return {
            "NamespaceTerminating": "KubernetesAgent",
            "PodCrash": "KubernetesAgent",
            "HighCPU": "MonitoringAgent",
            "DiskFull": "SystemAgent"
        }
    
    @staticmethod
    def create_custom_mappings(**overrides):
        """Create custom agent mappings."""
        base_data = {
            "CustomAlert": "CustomAgent",
            "AnotherAlert": "AnotherAgent",
            "TestAlert": "TestAgent"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_kubernetes_mappings():
        """Create Kubernetes-specific agent mappings."""
        return {
            "NamespaceTerminating": "KubernetesAgent",
            "PodCrash": "KubernetesAgent",
            "PodOOMKilled": "KubernetesAgent",
            "NodeNotReady": "KubernetesAgent"
        }
    
    @staticmethod
    def create_mixed_mappings():
        """Create mixed agent mappings for testing."""
        return {
            "NamespaceTerminating": "KubernetesAgent",
            "HighCPU": "MonitoringAgent",
            "DiskFull": "SystemAgent",
            "CustomAlert": "CustomAgent"
        }


class MCPServerFactory:
    """Factory for creating test MCP server configurations."""
    
    @staticmethod
    def create_kubernetes_server(**overrides):
        """Create a Kubernetes MCP server configuration."""
        base_data = {
            "server_id": "kubernetes-server",
            "server_type": "kubernetes",
            "enabled": True,
            "connection_params": {
                "command": "kubectl",
                "args": ["proxy", "--port=8001"],
                "env": {"KUBECONFIG": "/path/to/kubeconfig"}
            },
            "instructions": "Kubernetes MCP server for cluster operations"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_docker_server(**overrides):
        """Create a Docker MCP server configuration."""
        base_data = {
            "server_id": "docker-server",
            "server_type": "docker",
            "enabled": True,
            "connection_params": {
                "command": "docker",
                "args": ["run", "--rm", "-it"],
                "env": {"DOCKER_HOST": "unix:///var/run/docker.sock"}
            },
            "instructions": "Docker MCP server for container operations"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_test_server(**overrides):
        """Create a test MCP server configuration."""
        base_data = {
            "server_id": "test-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "command": "test",
                "args": ["--test"],
                "env": {}
            },
            "instructions": "Test MCP server for testing"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_disabled_server(**overrides):
        """Create a disabled MCP server configuration."""
        base_data = {
            "server_id": "disabled-server",
            "server_type": "test",
            "enabled": False,
            "connection_params": {
                "command": "disabled",
                "args": [],
                "env": {}
            },
            "instructions": "Disabled MCP server for testing"
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_custom_server(**overrides):
        """Create a custom MCP server configuration."""
        base_data = {
            "server_id": "custom-server",
            "server_type": "custom",
            "enabled": True,
            "connection_params": {
                "command": "custom",
                "args": ["--custom"],
                "env": {"CUSTOM_ENV": "custom_value"}
            },
            "instructions": "Custom MCP server for testing"
        }
        base_data.update(overrides)
        return base_data


class DashboardFactory:
    """Factory for creating test dashboard data."""
    
    @staticmethod
    def create_session_summary(**overrides):
        """Create a SessionSummary with sensible defaults."""
        from tarsy.services.dashboard_update_service import SessionSummary
        from datetime import datetime
        
        base_data = {
            "session_id": "test-session-123",
            "status": "active",
            "start_time": datetime.now(),
            "llm_interactions": 0,
            "mcp_communications": 0,
            "agent_type": "KubernetesAgent",
            "last_activity": datetime.now(),
            "errors_count": 0
        }
        base_data.update(overrides)
        return SessionSummary(**base_data)
    
    @staticmethod
    def create_llm_interaction_data(**overrides):
        """Create LLM interaction data with sensible defaults."""
        from datetime import datetime
        
        base_data = {
            'interaction_type': 'llm',
            'session_id': 'test-session-123',
            'step_description': 'LLM analysis using gpt-4',
            'model_used': 'gpt-4',
            'success': True,
            'duration_ms': 1500,
            'timestamp': datetime.now().isoformat(),
            'tool_calls_present': True,
            'error_message': None
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_mcp_interaction_data(**overrides):
        """Create MCP interaction data with sensible defaults."""
        from datetime import datetime
        
        base_data = {
            'interaction_type': 'mcp',
            'session_id': 'test-session-123',
            'server_id': 'kubernetes-server',
            'step_description': 'MCP communication with Kubernetes server',
            'success': True,
            'duration_ms': 800,
            'timestamp': datetime.now().isoformat(),
            'error_message': None
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_error_interaction_data(**overrides):
        """Create error interaction data with sensible defaults."""
        from datetime import datetime
        
        base_data = {
            'interaction_type': 'llm',
            'session_id': 'test-session-123',
            'step_description': 'LLM analysis failed',
            'model_used': 'gpt-4',
            'success': False,
            'duration_ms': 500,
            'timestamp': datetime.now().isoformat(),
            'tool_calls_present': False,
            'error_message': 'Connection timeout to LLM service'
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_mock_broadcaster():
        """Create a mock broadcaster with sensible defaults."""
        from unittest.mock import AsyncMock
        
        broadcaster = AsyncMock()
        broadcaster.broadcast_dashboard_update = AsyncMock(return_value=3)
        broadcaster.broadcast_session_update = AsyncMock(return_value=2)
        broadcaster.broadcast_system_health = AsyncMock(return_value=1)
        return broadcaster


class AgentServiceFactory:
    """Factory for creating test agent service dependencies and configurations."""
    
    @staticmethod
    def create_mock_dependencies():
        """Create mock dependencies for AgentFactory."""
        from unittest.mock import Mock
        from tarsy.integrations.llm.client import LLMClient
        from tarsy.integrations.mcp.client import MCPClient
        from tarsy.services.mcp_server_registry import MCPServerRegistry
        
        return {
            'llm_client': Mock(spec=LLMClient),
            'mcp_client': Mock(spec=MCPClient),
            'mcp_registry': Mock(spec=MCPServerRegistry)
        }
    
    @staticmethod
    def create_agent_configs(**overrides):
        """Create agent configurations for testing."""
        base_data = {
            'test-agent': {
                'agent_type': 'TestAgent',
                'enabled': True,
                'config': {'param1': 'value1', 'param2': 'value2'}
            },
            'custom-agent': {
                'agent_type': 'CustomAgent',
                'enabled': False,
                'config': {'custom_param': 'custom_value'}
            }
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_mock_agent_instance():
        """Create a mock agent instance."""
        from unittest.mock import Mock
        
        mock_agent = Mock()
        mock_agent.agent_type = "KubernetesAgent"
        mock_agent.llm_client = Mock()
        mock_agent.mcp_client = Mock()
        mock_agent.mcp_registry = Mock()
        return mock_agent
    
    @staticmethod
    def create_mock_kubernetes_agent():
        """Create a mock KubernetesAgent class."""
        from unittest.mock import Mock
        
        mock_agent_class = Mock()
        mock_agent_instance = AgentServiceFactory.create_mock_agent_instance()
        mock_agent_class.return_value = mock_agent_instance
        return mock_agent_class, mock_agent_instance


class RunbookFactory:
    """Factory for creating test runbook service data and configurations."""
    
    @staticmethod
    def create_mock_settings(**overrides):
        """Create mock settings for RunbookService."""
        from unittest.mock import Mock
        from tarsy.config.settings import Settings
        
        base_data = {
            'github_token': None
        }
        base_data.update(overrides)
        
        settings = Mock(spec=Settings)
        settings.github_token = base_data['github_token']
        return settings
    
    @staticmethod
    def create_mock_response(**overrides):
        """Create mock HTTP response."""
        from unittest.mock import Mock
        
        base_data = {
            'text': "# Runbook Content\n\nThis is a test runbook.",
            'status_code': 200
        }
        base_data.update(overrides)
        
        response = Mock()
        response.text = base_data['text']
        response.status_code = base_data['status_code']
        response.raise_for_status = Mock()
        return response
    
    @staticmethod
    def create_test_urls():
        """Create test URLs for runbook service testing."""
        return {
            'github_blob': "https://github.com/user/repo/blob/master/docs/runbook.md",
            'github_raw': "https://raw.githubusercontent.com/user/repo/master/docs/runbook.md",
            'non_github': "https://example.com/docs/runbook.md",
            'malformed': "https://github.com/user/repo/blob/master",
            'special_chars': "https://github.com/user/repo/blob/feature/fix-bug/docs/run%20book.md"
        }
    
    @staticmethod
    def create_error_responses():
        """Create various error responses for testing."""
        import httpx
        from unittest.mock import Mock
        
        return {
            'http_404': httpx.HTTPStatusError("404 Client Error: Not Found", request=Mock(), response=Mock()),
            'network_error': httpx.NetworkError("Network connection failed"),
            'timeout_error': httpx.TimeoutException("Request timed out"),
            'response_status_error': "mock_response"  # Special case for response status error
        }


class DataMaskingFactory:
    """
    Factory for creating test data masking service data and configurations.
    
    Use when: You need test data with sensitive information for masking tests
    
    Examples:
        # Create test data with secrets
        secrets = DataMaskingFactory.create_test_data_with_secrets()
        
        # Create Kubernetes secret data
        k8s_secret = DataMaskingFactory.create_kubernetes_secret_data()
        
        # Create pattern groups
        patterns = DataMaskingFactory.create_pattern_groups()
        
        # Create nested data structure
        nested_data = DataMaskingFactory.create_nested_data_structure()
        
        # Create base64 test data
        base64_data = DataMaskingFactory.create_base64_test_data()
    
    Best practices:
        - Use for testing data masking functionality
        - Contains realistic sensitive data patterns for comprehensive testing
        - Override fields to test specific masking scenarios
    """
    
    @staticmethod
    def create_masking_config(**overrides):
        """Create a data masking configuration."""
        base_data = {
            "masking_enabled": True,
            "masking_rules": [
                {
                    "field": "password",
                    "mask_char": "*",
                    "mask_length": 10
                },
                {
                    "field": "credit_card",
                    "mask_char": "X",
                    "mask_length": 16
                }
            ]
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_masking_rules(**overrides):
        """Create a list of masking rules."""
        base_data = [
            {
                "field": "password",
                "mask_char": "*",
                "mask_length": 10
            },
            {
                "field": "credit_card",
                "mask_char": "X",
                "mask_length": 16
            }
        ]
        base_data.update(overrides)
        return base_data

    @staticmethod
    def create_test_data_with_secrets(**overrides):
        """Create test data containing sensitive information."""
        base_data = {
            "api_key": "sk_test_123456789012345678901234567890",
            "password": "mySecretPassword123",
            "token": "dGhpc2lzYWxvbmdlcmJhc2U2NGVuY29kZWR2YWx1ZQ==",
            "normal_field": "normal_value",
            "number_field": 42,
            "boolean_field": True,
            "null_field": None
        }
        base_data.update(overrides)
        return base_data

    @staticmethod
    def create_kubernetes_secret_data():
        """Create Kubernetes secret data for testing."""
        return '''apiVersion: v1
data:
  username: YWRtaW4=
  password: c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==
  somekey: xyz
kind: Secret
metadata:
  name: my-secret
  namespace: superman-dev'''

    @staticmethod
    def create_base64_test_data():
        """Create test data with base64 encoded values."""
        return {
            "token": "dGhpc2lzYWxvbmdlcmJhc2U2NGVuY29kZWR2YWx1ZQ==",
            "another_field": "c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==",
            "username": "YWRtaW4=",
            "password": "cGFzcw==",
            "short_token": "dGVzdA=="
        }

    @staticmethod
    def create_nested_data_structure():
        """Create a nested data structure for testing."""
        return {
            "result": {
                "config": "api_key: sk_123456789012345678901234567890",
                "normal_field": "normal_value"
            },
            "string_field": "password: secret123",
            "number_field": 42,
            "boolean_field": True,
            "null_field": None,
            "nested": {
                "array": ["api_key: sk_123456789012345678901234567890"]
            }
        }

    @staticmethod
    def create_pattern_groups():
        """Create pattern groups for testing."""
        return {
            "basic": ["api_key", "password"],
            "security": ["token", "certificate"],
            "kubernetes": ["kubernetes_data_section", "kubernetes_stringdata_json"],
            "unknown_group": ["unknown_pattern"]
        }


class DashboardConnectionFactory:
    """Factory for creating test dashboard connection manager data and configurations."""
    
    # Note: Use TestUtils.create_mock_websocket() instead for WebSocket mocks
    
    @staticmethod
    def create_test_message(**overrides):
        """Create a test message for WebSocket communication."""
        from datetime import datetime
        
        base_data = {
            "type": "test",
            "data": "hello",
            "timestamp": datetime(2023, 1, 1, 12, 0, 0)
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_subscription_data(**overrides):
        """Create subscription data for testing."""
        from tarsy.models.websocket_models import ChannelType
        
        base_data = {
            "user_id": "test_user",
            "channel": ChannelType.DASHBOARD_UPDATES,
            "subscriptions": {"dashboard_updates", "session_123"}
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_connection_data(**overrides):
        """Create connection data for testing."""
        base_data = {
            "user_id": "test_user",
            "is_active": True,
            "has_subscriptions": True
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_channel_subscribers(**overrides):
        """Create channel subscribers data for testing."""
        from tarsy.models.websocket_models import ChannelType
        
        base_data = {
            ChannelType.DASHBOARD_UPDATES: {"user1", "user2", "user3"},
            ChannelType.SYSTEM_HEALTH: {"user1"},
            "session_123": {"user2"}
        }
        base_data.update(overrides)
        return base_data


class MCPServerMaskingFactory:
    """
    Factory for creating test MCP server masking and template configuration data.
    
    Use when: You need complex MCP server configurations with masking or templates
    
    Examples:
        # Create server configurations with masking
        basic_config = MCPServerMaskingFactory.create_test_server_config()
        secure_config = MCPServerMaskingFactory.create_secure_server_config()
        
        # Create template configurations
        template_config = MCPServerMaskingFactory.create_template_server_config()
        complex_template = MCPServerMaskingFactory.create_complex_template_server_config()
        
        # Create environment variables for templates
        env_vars = MCPServerMaskingFactory.create_template_environment_vars()
        
        # Create masking configurations
        basic_masking = MCPServerMaskingFactory.create_basic_masking_config()
        comprehensive_masking = MCPServerMaskingFactory.create_comprehensive_masking_config()
    
    Best practices:
        - Use for MCP server registry tests with complex configurations
        - Supports both masking and template functionality
        - Override specific fields for custom test scenarios
        - Use appropriate method for your test complexity level
    """
    
    @staticmethod
    def create_basic_masking_config(**overrides):
        """Create a basic masking configuration."""
        base_data = {
            "enabled": True,
            "pattern_groups": ["basic"]
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_comprehensive_masking_config(**overrides):
        """Create a comprehensive masking configuration."""
        base_data = {
            "enabled": True,
            "pattern_groups": ["security"],
            "patterns": ["token"],
            "custom_patterns": [
                {
                    "name": "server_id",
                    "pattern": r"server_id_\d{8}",
                    "replacement": "***MASKED_SERVER_ID***",
                    "description": "Server internal IDs",
                    "enabled": True
                }
            ]
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_disabled_masking_config(**overrides):
        """Create a disabled masking configuration."""
        base_data = {
            "enabled": False,
            "pattern_groups": []
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_test_server_config(**overrides):
        """Create a test server configuration with masking."""
        base_data = {
            "server_id": "test-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {"command": "test", "args": []},
            "instructions": "Test server with masking",
            "data_masking": MCPServerMaskingFactory.create_basic_masking_config()
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_secure_server_config(**overrides):
        """Create a secure server configuration with comprehensive masking."""
        base_data = {
            "server_id": "secure-server",
            "server_type": "secure",
            "enabled": True,
            "connection_params": {"command": "secure", "args": []},
            "instructions": "Secure server with comprehensive masking",
            "data_masking": MCPServerMaskingFactory.create_comprehensive_masking_config()
        }
        base_data.update(overrides)
        return base_data
    
    # Removed create_server_configs_dict - create individual configs as needed

    @staticmethod
    def create_template_server_config(**overrides):
        """Create a server configuration with template variables."""
        base_data = {
            "server_id": "template-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "command": "test-server",
                "args": ["--token", "${TEST_TOKEN}", "--url", "${TEST_URL}"]
            }
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_complex_template_server_config(**overrides):
        """Create a complex server configuration with multiple template variables."""
        base_data = {
            "server_id": "complex-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "command": "complex-${SERVER_TYPE}",
                "args": ["--endpoint", "https://${HOST}:${PORT}/api"],
                "env": {
                    "CONFIG_PATH": "${KUBECONFIG}",
                    "AUTH_TOKEN": "${AUTH_TOKEN}"
                }
            }
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_failing_template_server_config(**overrides):
        """Create a server configuration with template that will fail."""
        base_data = {
            "server_id": "failing-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "args": ["--missing", "${DEFINITELY_MISSING_VAR}"]
            }
        }
        base_data.update(overrides)
        return base_data
    
    @staticmethod
    def create_template_environment_vars(**overrides):
        """Create environment variables for template testing."""
        base_data = {
            'TEST_TOKEN': 'secret123',
            'TEST_URL': 'http://test.com',
            'SERVER_TYPE': 'production',
            'HOST': 'api.company.com',
            'PORT': '8443',
            'AUTH_TOKEN': 'bearer-token-123',
            'KUBECONFIG': '/home/.kube/config'
        }
        base_data.update(overrides)
        return base_data

