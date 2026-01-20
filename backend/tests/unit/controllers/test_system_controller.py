"""Unit tests for system controller."""

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app
from tarsy.services.system_warnings_service import SystemWarningsService


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_warnings_singleton() -> None:
    """Reset warnings singleton before each test."""
    SystemWarningsService._instance = None


@pytest.mark.unit
def test_get_system_warnings_empty(client: TestClient) -> None:
    """Test getting system warnings when none exist."""
    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.unit
def test_get_system_warnings_with_warnings(client: TestClient) -> None:
    """Test getting system warnings when warnings exist."""
    from tarsy.models.system_models import WarningCategory
    from tarsy.services.system_warnings_service import get_warnings_service

    # Add some warnings
    warnings_service = get_warnings_service()
    warnings_service.add_warning(
        WarningCategory.MCP_INITIALIZATION,
        "MCP Server 'kubernetes-server' failed to initialize",
        "Connection timeout after 30 seconds",
    )
    warnings_service.add_warning(
        WarningCategory.RUNBOOK_SERVICE,
        "Runbook service disabled",
        "Set GITHUB_TOKEN environment variable",
    )

    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2

    # Check first warning
    assert data[0]["category"] == WarningCategory.MCP_INITIALIZATION
    assert data[0]["message"] == "MCP Server 'kubernetes-server' failed to initialize"
    assert data[0]["details"] == "Connection timeout after 30 seconds"
    assert "warning_id" in data[0]
    assert "timestamp" in data[0]

    # Check second warning
    assert data[1]["category"] == WarningCategory.RUNBOOK_SERVICE
    assert data[1]["message"] == "Runbook service disabled"
    assert data[1]["details"] == "Set GITHUB_TOKEN environment variable"
    assert "warning_id" in data[1]
    assert "timestamp" in data[1]


@pytest.mark.unit
def test_get_system_warnings_response_format(client: TestClient) -> None:
    """Test that system warnings response follows correct format."""
    from tarsy.services.system_warnings_service import get_warnings_service

    warnings_service = get_warnings_service()
    warnings_service.add_warning("test_category", "test message", "test details")

    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    warning = data[0]
    assert isinstance(warning, dict)
    assert set(warning.keys()) == {
        "warning_id",
        "category",
        "message",
        "details",
        "timestamp",
        "server_id",
    }
    assert isinstance(warning["warning_id"], str)
    assert isinstance(warning["category"], str)
    assert isinstance(warning["message"], str)
    assert isinstance(warning["timestamp"], int)
    # server_id can be None or str
    assert warning["server_id"] is None or isinstance(warning["server_id"], str)


@pytest.mark.unit
def test_get_system_warnings_without_details(client: TestClient) -> None:
    """Test getting system warnings when details field is None."""
    from tarsy.services.system_warnings_service import get_warnings_service

    warnings_service = get_warnings_service()
    warnings_service.add_warning("test_category", "test message")

    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["details"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_success_with_cache(client: TestClient) -> None:
    """Test successfully retrieving MCP servers and their tools from cache."""
    from unittest.mock import Mock, patch

    from mcp.types import Tool
    
    # Create mock alert_service with cached tools
    mock_alert_service = Mock()
    
    # Mock health monitor with cached tools
    mock_health_monitor = Mock()
    cached_tools = {
        "kubernetes-server": [
            Tool(name="kubectl-get", description="Get Kubernetes resources", inputSchema={"type": "object"}),
            Tool(name="kubectl-describe", description="Describe Kubernetes resources", inputSchema={"type": "object"})
        ],
        "argocd-server": [
            Tool(name="get-application", description="Get ArgoCD application", inputSchema={"type": "object"})
        ]
    }
    mock_health_monitor.get_cached_tools.return_value = cached_tools
    mock_alert_service.mcp_health_monitor = mock_health_monitor
    
    # Mock MCP server registry
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server"]
    
    # Mock server configs
    k8s_config = Mock()
    
    argocd_config = Mock()
    
    def mock_get_server_config(server_id):
        if server_id == "kubernetes-server":
            return k8s_config
        elif server_id == "argocd-server":
            return argocd_config
        raise ValueError(f"Server {server_id} not found")
    
    mock_registry.get_server_config.side_effect = mock_get_server_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    # Patch alert_service in main module
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    
    assert "servers" in data
    assert len(data["servers"]) == 2
    
    # Verify kubernetes-server
    k8s_server = next(s for s in data["servers"] if s["server_id"] == "kubernetes-server")
    assert len(k8s_server["tools"]) == 2
    assert any(t["name"] == "kubectl-get" for t in k8s_server["tools"])
    assert any(t["name"] == "kubectl-describe" for t in k8s_server["tools"])
    
    # Verify argocd-server
    argocd_server = next(s for s in data["servers"] if s["server_id"] == "argocd-server")
    assert len(argocd_server["tools"]) == 1
    assert argocd_server["tools"][0]["name"] == "get-application"
    
    # Verify cache was used
    mock_health_monitor.get_cached_tools.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_fallback_to_direct_query(client: TestClient) -> None:
    """Test fallback to direct MCP queries when cache is empty (startup period)."""
    from unittest.mock import AsyncMock, Mock, patch

    from mcp.types import Tool
    
    # Create mock alert_service with empty cache
    mock_alert_service = Mock()
    
    # Mock health monitor with empty cache
    mock_health_monitor = Mock()
    mock_health_monitor.get_cached_tools.return_value = {}  # Empty cache
    mock_alert_service.mcp_health_monitor = mock_health_monitor
    
    # Mock MCP client for fallback
    mock_mcp_client = AsyncMock()
    mock_mcp_client_factory = Mock()
    mock_mcp_client_factory.create_client = AsyncMock(return_value=mock_mcp_client)
    mock_alert_service.mcp_client_factory = mock_mcp_client_factory
    
    # Mock MCP server registry
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = ["kubernetes-server"]
    
    # Mock server config
    k8s_config = Mock()
    k8s_config.server_id = "kubernetes-server"
    k8s_config.server_type = "kubernetes"
    k8s_config.enabled = True
    mock_registry.get_server_config.return_value = k8s_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    # Mock list_tools_simple response
    async def mock_list_tools_simple(server_name=None):
        return {
            "kubernetes-server": [
                Tool(name="kubectl-get", description="Get Kubernetes resources", inputSchema={"type": "object"})
            ]
        }
    
    mock_mcp_client.list_tools_simple = AsyncMock(side_effect=mock_list_tools_simple)
    mock_mcp_client.close = AsyncMock()
    
    # Patch alert_service in main module
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    
    assert "servers" in data
    assert len(data["servers"]) == 1
    
    # Verify kubernetes-server
    k8s_server = data["servers"][0]
    assert k8s_server["server_id"] == "kubernetes-server"
    assert len(k8s_server["tools"]) == 1
    
    # Verify fallback was used
    mock_health_monitor.get_cached_tools.assert_called_once()
    mock_mcp_client_factory.create_client.assert_called_once()
    mock_mcp_client.close.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_service_not_initialized(client: TestClient) -> None:
    """Test error when alert_service is not initialized."""
    from unittest.mock import patch
    
    # Patch alert_service to None
    with patch("tarsy.main.alert_service", None):
        response = client.get("/api/v1/system/mcp-servers")
    
    assert response.status_code == 503
    assert "Service not initialized" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_empty_registry(client: TestClient) -> None:
    """Test retrieving MCP servers when no servers are configured."""
    from unittest.mock import Mock, patch
    
    # Create mock alert_service with empty registry
    mock_alert_service = Mock()
    
    # Mock health monitor with cached tools
    mock_health_monitor = Mock()
    # Return non-empty dict to use cached path (even though it has no actual servers)
    mock_health_monitor.get_cached_tools.return_value = {"__sentinel__": []}
    mock_alert_service.mcp_health_monitor = mock_health_monitor
    
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = []
    mock_alert_service.mcp_server_registry = mock_registry
    
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    assert response.status_code == 200
    data = response.json()
    assert "servers" in data
    assert len(data["servers"]) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_partial_cache(client: TestClient) -> None:
    """Test handling when some servers have cached tools and others don't."""
    from unittest.mock import Mock, patch

    from mcp.types import Tool
    
    mock_alert_service = Mock()
    
    # Mock health monitor with partial cache (one server missing)
    mock_health_monitor = Mock()
    cached_tools = {
        "working-server": [
            Tool(name="test-tool", description="Test", inputSchema={})
        ]
        # "failing-server" not in cache - simulates it never became healthy
    }
    mock_health_monitor.get_cached_tools.return_value = cached_tools
    mock_alert_service.mcp_health_monitor = mock_health_monitor
    
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = ["working-server", "failing-server"]
    
    # Mock configs
    working_config = Mock()
    working_config.server_id = "working-server"
    working_config.server_type = "test"
    working_config.enabled = True
    
    failing_config = Mock()
    failing_config.server_id = "failing-server"
    failing_config.server_type = "test"
    failing_config.enabled = True
    
    def mock_get_server_config(server_id):
        if server_id == "working-server":
            return working_config
        elif server_id == "failing-server":
            return failing_config
        raise ValueError(f"Server {server_id} not found")
    
    mock_registry.get_server_config.side_effect = mock_get_server_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    # Request should still succeed
    assert response.status_code == 200
    data = response.json()
    
    # Both servers should be in response
    assert len(data["servers"]) == 2
    
    # Working server should have tools
    working_server = next(s for s in data["servers"] if s["server_id"] == "working-server")
    assert len(working_server["tools"]) == 1
    
    # Failing server should have no tools (not in cache yet)
    failing_server = next(s for s in data["servers"] if s["server_id"] == "failing-server")
    assert len(failing_server["tools"]) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_success(client: TestClient) -> None:
    """Test successfully retrieving default tools configuration for default alert type."""
    from unittest.mock import Mock, patch
    
    # Create mock alert_service
    mock_alert_service = Mock()
    
    # Mock chain registry
    mock_chain_registry = Mock()
    mock_chain_registry.get_default_alert_type.return_value = "NamespaceAlertK8s"
    
    # Mock chain config with stages
    mock_chain_config = Mock()
    mock_stage1 = Mock()
    mock_stage1.agent = "kubernetes-agent"
    mock_stage2 = Mock()
    mock_stage2.agent = "final-analysis-agent"
    mock_chain_config.stages = [mock_stage1, mock_stage2]
    mock_chain_registry.get_chain_for_alert_type.return_value = mock_chain_config
    mock_alert_service.chain_registry = mock_chain_registry
    
    # Mock agent factory
    mock_agent_factory = Mock()
    mock_agent_factory.agent_configs = {
        "kubernetes-agent": Mock(mcp_servers=["kubernetes-server"]),
        "final-analysis-agent": Mock(mcp_servers=["argocd-server"])
    }
    mock_alert_service.agent_factory = mock_agent_factory
    
    # Mock MCP server registry
    mock_registry = Mock()
    k8s_config = Mock()
    k8s_config.server_id = "kubernetes-server"
    k8s_config.server_type = "kubernetes"
    
    argocd_config = Mock()
    argocd_config.server_id = "argocd-server"
    argocd_config.server_type = "argocd"
    
    def mock_get_server_config(server_id):
        if server_id == "kubernetes-server":
            return k8s_config
        elif server_id == "argocd-server":
            return argocd_config
        raise ValueError(f"Server {server_id} not found")
    
    mock_registry.get_server_config.side_effect = mock_get_server_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    # Mock settings
    mock_settings = Mock()
    mock_provider_config = Mock()
    mock_provider_config.native_tools = None  # Default: all enabled
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-default"
    
    # Patch both alert_service and settings
    with patch("tarsy.main.alert_service", mock_alert_service), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools")
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    
    # Check structure
    assert "alert_type" in data
    assert "mcp_servers" in data
    assert "native_tools" in data
    
    # Verify alert type
    assert data["alert_type"] == "NamespaceAlertK8s"
    
    # Verify MCP servers (from chain's agents)
    assert len(data["mcp_servers"]) == 2
    server_ids = [s["server_id"] for s in data["mcp_servers"]]
    assert "kubernetes-server" in server_ids
    assert "argocd-server" in server_ids
    
    # Verify native tools (default: search and url_context enabled, code_execution disabled)
    assert data["native_tools"]["google_search"] is True
    assert data["native_tools"]["code_execution"] is False
    assert data["native_tools"]["url_context"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_with_custom_native_tools(client: TestClient) -> None:
    """Test default tools with custom native tools configuration."""
    from unittest.mock import Mock, patch
    
    mock_alert_service = Mock()
    
    # Mock chain registry and chain config
    mock_chain_registry = Mock()
    mock_chain_registry.get_default_alert_type.return_value = "TestAlert"
    mock_chain_config = Mock()
    mock_stage = Mock()
    mock_stage.agent = "test-agent"
    mock_chain_config.stages = [mock_stage]
    mock_chain_registry.get_chain_for_alert_type.return_value = mock_chain_config
    mock_alert_service.chain_registry = mock_chain_registry
    
    # Mock agent factory
    mock_agent_factory = Mock()
    mock_agent_factory.agent_configs = {
        "test-agent": Mock(mcp_servers=["test-server"])
    }
    mock_alert_service.agent_factory = mock_agent_factory
    
    # Mock MCP server registry
    mock_registry = Mock()
    test_config = Mock()
    test_config.server_id = "test-server"
    test_config.server_type = "test"
    mock_registry.get_server_config.return_value = test_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    # Mock settings with custom native tools
    mock_settings = Mock()
    mock_provider_config = Mock()
    # Custom config: only google_search and url_context enabled
    mock_provider_config.native_tools = {
        "google_search": True,
        "code_execution": False,
        "url_context": True
    }
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-custom"
    
    with patch("tarsy.main.alert_service", mock_alert_service), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify custom native tools configuration
    assert data["native_tools"]["google_search"] is True
    assert data["native_tools"]["code_execution"] is False
    assert data["native_tools"]["url_context"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_no_mcp_servers(client: TestClient) -> None:
    """Test default tools when chain agents have no MCP servers configured."""
    from unittest.mock import Mock, patch
    
    mock_alert_service = Mock()
    
    # Mock chain registry with agent that has no MCP servers
    mock_chain_registry = Mock()
    mock_chain_registry.get_default_alert_type.return_value = "SimpleAlert"
    mock_chain_config = Mock()
    mock_stage = Mock()
    mock_stage.agent = "simple-agent"
    mock_chain_config.stages = [mock_stage]
    mock_chain_registry.get_chain_for_alert_type.return_value = mock_chain_config
    mock_alert_service.chain_registry = mock_chain_registry
    
    # Mock agent factory with agent that has no MCP servers
    mock_agent_factory = Mock()
    mock_agent_factory.agent_configs = {
        "simple-agent": Mock(mcp_servers=[])  # No servers
    }
    mock_alert_service.agent_factory = mock_agent_factory
    mock_alert_service.mcp_server_registry = Mock()
    
    mock_settings = Mock()
    mock_provider_config = Mock()
    mock_provider_config.native_tools = None
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-default"
    
    with patch("tarsy.main.alert_service", mock_alert_service), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should still succeed with empty servers list
    assert data["mcp_servers"] == []
    assert data["native_tools"]["google_search"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_with_specific_alert_type(client: TestClient) -> None:
    """Test getting defaults for a specific alert type."""
    from unittest.mock import Mock, patch
    
    mock_alert_service = Mock()
    
    # Mock chain registry
    mock_chain_registry = Mock()
    mock_chain_config = Mock()
    mock_stage = Mock()
    mock_stage.agent = "specialized-agent"
    mock_chain_config.stages = [mock_stage]
    mock_chain_registry.get_chain_for_alert_type.return_value = mock_chain_config
    mock_alert_service.chain_registry = mock_chain_registry
    
    # Mock agent factory with specialized agent
    mock_agent_factory = Mock()
    mock_agent_factory.agent_configs = {
        "specialized-agent": Mock(mcp_servers=["specialized-server"])
    }
    mock_alert_service.agent_factory = mock_agent_factory
    
    # Mock MCP server registry
    mock_registry = Mock()
    specialized_config = Mock()
    specialized_config.server_id = "specialized-server"
    specialized_config.server_type = "specialized"
    mock_registry.get_server_config.return_value = specialized_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    mock_settings = Mock()
    mock_provider_config = Mock()
    mock_provider_config.native_tools = None
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-default"
    
    with patch("tarsy.main.alert_service", mock_alert_service), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools?alert_type=CustomAlert")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify alert type
    assert data["alert_type"] == "CustomAlert"
    
    # Verify it used the chain for CustomAlert
    mock_chain_registry.get_chain_for_alert_type.assert_called_with("CustomAlert")
    
    # Verify the correct server is returned
    assert len(data["mcp_servers"]) == 1
    assert data["mcp_servers"][0]["server_id"] == "specialized-server"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_invalid_alert_type(client: TestClient) -> None:
    """Test error when alert_type is invalid."""
    from unittest.mock import Mock, patch
    
    mock_alert_service = Mock()
    
    # Mock chain registry that raises ValueError for invalid alert type
    mock_chain_registry = Mock()
    mock_chain_registry.get_chain_for_alert_type.side_effect = ValueError("No chain found for alert type 'InvalidType'")
    mock_alert_service.chain_registry = mock_chain_registry
    
    mock_settings = Mock()
    mock_provider_config = Mock()
    mock_provider_config.native_tools = None
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-default"
    
    with patch("tarsy.main.alert_service", mock_alert_service), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools?alert_type=InvalidType")
    
    assert response.status_code == 400
    assert "No chain found" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_service_not_initialized(client: TestClient) -> None:
    """Test error when alert_service is not initialized."""
    from unittest.mock import Mock, patch
    
    # Mock settings (will be accessed before checking alert_service)
    mock_settings = Mock()
    mock_provider_config = Mock()
    mock_provider_config.native_tools = None
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-default"
    
    with patch("tarsy.main.alert_service", None), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools")
    
    assert response.status_code == 503
    assert "Service not initialized" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_default_tools_handles_server_config_error(client: TestClient) -> None:
    """Test that endpoint handles errors when fetching individual server configs gracefully."""
    from unittest.mock import Mock, patch
    
    mock_alert_service = Mock()
    
    # Mock chain registry
    mock_chain_registry = Mock()
    mock_chain_registry.get_default_alert_type.return_value = "TestAlert"
    mock_chain_config = Mock()
    mock_stage = Mock()
    mock_stage.agent = "test-agent"
    mock_chain_config.stages = [mock_stage]
    mock_chain_registry.get_chain_for_alert_type.return_value = mock_chain_config
    mock_alert_service.chain_registry = mock_chain_registry
    
    # Mock agent factory with agent that uses both servers
    mock_agent_factory = Mock()
    mock_agent_factory.agent_configs = {
        "test-agent": Mock(mcp_servers=["good-server", "bad-server"])
    }
    mock_alert_service.agent_factory = mock_agent_factory
    
    # Mock MCP server registry
    mock_registry = Mock()
    good_config = Mock()
    good_config.server_id = "good-server"
    good_config.server_type = "test"
    
    def mock_get_server_config(server_id):
        if server_id == "good-server":
            return good_config
        elif server_id == "bad-server":
            raise Exception("Failed to get config")
        raise ValueError(f"Server {server_id} not found")
    
    mock_registry.get_server_config.side_effect = mock_get_server_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    mock_settings = Mock()
    mock_provider_config = Mock()
    mock_provider_config.native_tools = None
    mock_settings.get_llm_config.return_value = mock_provider_config
    mock_settings.llm_provider = "google-default"
    
    with patch("tarsy.main.alert_service", mock_alert_service), \
         patch("tarsy.controllers.system_controller.get_settings", return_value=mock_settings):
        response = client.get("/api/v1/system/default-tools")
    
    # Should succeed despite error with one server
    assert response.status_code == 200
    data = response.json()
    
    # Only good server should be included
    assert len(data["mcp_servers"]) == 1
    assert data["mcp_servers"][0]["server_id"] == "good-server"
