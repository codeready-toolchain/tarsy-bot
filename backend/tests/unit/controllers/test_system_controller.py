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
async def test_get_mcp_servers_success(client: TestClient) -> None:
    """Test successfully retrieving MCP servers and their tools."""
    from unittest.mock import AsyncMock, Mock, patch
    from mcp.types import Tool
    
    # Create mock alert_service with required components
    mock_alert_service = Mock()
    mock_mcp_client = AsyncMock()
    mock_mcp_client_factory = Mock()
    mock_mcp_client_factory.create_client = AsyncMock(return_value=mock_mcp_client)
    mock_alert_service.mcp_client_factory = mock_mcp_client_factory
    
    # Mock MCP server registry
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server"]
    
    # Mock server configs
    k8s_config = Mock()
    k8s_config.server_id = "kubernetes-server"
    k8s_config.server_type = "kubernetes"
    k8s_config.enabled = True
    
    argocd_config = Mock()
    argocd_config.server_id = "argocd-server"
    argocd_config.server_type = "argocd"
    argocd_config.enabled = True
    
    def mock_get_server_config(server_id):
        if server_id == "kubernetes-server":
            return k8s_config
        elif server_id == "argocd-server":
            return argocd_config
        raise ValueError(f"Server {server_id} not found")
    
    mock_registry.get_server_config.side_effect = mock_get_server_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    # Mock list_tools_simple response
    async def mock_list_tools_simple(server_name=None):
        if server_name == "kubernetes-server":
            return {
                "kubernetes-server": [
                    Tool(name="kubectl-get", description="Get Kubernetes resources", inputSchema={"type": "object"}),
                    Tool(name="kubectl-describe", description="Describe Kubernetes resources", inputSchema={"type": "object"})
                ]
            }
        elif server_name == "argocd-server":
            return {
                "argocd-server": [
                    Tool(name="get-application", description="Get ArgoCD application", inputSchema={"type": "object"})
                ]
            }
        return {}
    
    mock_mcp_client.list_tools_simple = AsyncMock(side_effect=mock_list_tools_simple)
    mock_mcp_client.cleanup = AsyncMock()
    
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
    assert k8s_server["server_type"] == "kubernetes"
    assert k8s_server["enabled"] is True
    assert len(k8s_server["tools"]) == 2
    assert any(t["name"] == "kubectl-get" for t in k8s_server["tools"])
    assert any(t["name"] == "kubectl-describe" for t in k8s_server["tools"])
    
    # Verify argocd-server
    argocd_server = next(s for s in data["servers"] if s["server_id"] == "argocd-server")
    assert argocd_server["server_type"] == "argocd"
    assert argocd_server["enabled"] is True
    assert len(argocd_server["tools"]) == 1
    assert argocd_server["tools"][0]["name"] == "get-application"
    
    # Verify cleanup was called
    mock_mcp_client.cleanup.assert_called_once()


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
    from unittest.mock import AsyncMock, Mock, patch
    
    # Create mock alert_service with empty registry
    mock_alert_service = Mock()
    mock_mcp_client = AsyncMock()
    mock_mcp_client_factory = Mock()
    mock_mcp_client_factory.create_client = AsyncMock(return_value=mock_mcp_client)
    mock_alert_service.mcp_client_factory = mock_mcp_client_factory
    
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = []
    mock_alert_service.mcp_server_registry = mock_registry
    
    mock_mcp_client.cleanup = AsyncMock()
    
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    assert response.status_code == 200
    data = response.json()
    assert "servers" in data
    assert len(data["servers"]) == 0
    
    # Verify cleanup was called
    mock_mcp_client.cleanup.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_with_disabled_server(client: TestClient) -> None:
    """Test retrieving MCP servers including disabled ones."""
    from unittest.mock import AsyncMock, Mock, patch
    from mcp.types import Tool
    
    mock_alert_service = Mock()
    mock_mcp_client = AsyncMock()
    mock_mcp_client_factory = Mock()
    mock_mcp_client_factory.create_client = AsyncMock(return_value=mock_mcp_client)
    mock_alert_service.mcp_client_factory = mock_mcp_client_factory
    
    mock_registry = Mock()
    mock_registry.get_all_server_ids.return_value = ["enabled-server", "disabled-server"]
    
    # Mock configs with one disabled
    enabled_config = Mock()
    enabled_config.server_id = "enabled-server"
    enabled_config.server_type = "test"
    enabled_config.enabled = True
    
    disabled_config = Mock()
    disabled_config.server_id = "disabled-server"
    disabled_config.server_type = "test"
    disabled_config.enabled = False
    
    def mock_get_server_config(server_id):
        if server_id == "enabled-server":
            return enabled_config
        elif server_id == "disabled-server":
            return disabled_config
        raise ValueError(f"Server {server_id} not found")
    
    mock_registry.get_server_config.side_effect = mock_get_server_config
    mock_alert_service.mcp_server_registry = mock_registry
    
    # Mock list_tools_simple
    async def mock_list_tools_simple(server_name=None):
        return {
            server_name: [
                Tool(name=f"{server_name}-tool", description="Test tool", inputSchema={})
            ]
        }
    
    mock_mcp_client.list_tools_simple = AsyncMock(side_effect=mock_list_tools_simple)
    mock_mcp_client.cleanup = AsyncMock()
    
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    assert response.status_code == 200
    data = response.json()
    
    # Both servers should be returned
    assert len(data["servers"]) == 2
    
    # Verify enabled status
    enabled_server = next(s for s in data["servers"] if s["server_id"] == "enabled-server")
    assert enabled_server["enabled"] is True
    
    disabled_server = next(s for s in data["servers"] if s["server_id"] == "disabled-server")
    assert disabled_server["enabled"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_mcp_servers_tool_listing_failure(client: TestClient) -> None:
    """Test handling when tool listing fails for a server."""
    from unittest.mock import AsyncMock, Mock, patch
    from mcp.types import Tool
    
    mock_alert_service = Mock()
    mock_mcp_client = AsyncMock()
    mock_mcp_client_factory = Mock()
    mock_mcp_client_factory.create_client = AsyncMock(return_value=mock_mcp_client)
    mock_alert_service.mcp_client_factory = mock_mcp_client_factory
    
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
    
    # Mock list_tools_simple - one works, one fails
    async def mock_list_tools_simple(server_name=None):
        if server_name == "working-server":
            return {
                "working-server": [
                    Tool(name="test-tool", description="Test", inputSchema={})
                ]
            }
        else:
            raise Exception("Server communication failed")
    
    mock_mcp_client.list_tools_simple = AsyncMock(side_effect=mock_list_tools_simple)
    mock_mcp_client.cleanup = AsyncMock()
    
    with patch("tarsy.main.alert_service", mock_alert_service):
        response = client.get("/api/v1/system/mcp-servers")
    
    # Request should still succeed (partial success)
    assert response.status_code == 200
    data = response.json()
    
    # Should have at least the working server
    assert len(data["servers"]) >= 1
    working_server = next((s for s in data["servers"] if s["server_id"] == "working-server"), None)
    assert working_server is not None
    assert len(working_server["tools"]) == 1
