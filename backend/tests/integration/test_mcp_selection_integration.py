"""
Integration tests for MCP server/tool selection feature.

Tests alert submission with MCP selection and MCP servers discovery endpoint.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client for FastAPI app."""
    return TestClient(app)


class TestMCPServersEndpointIntegration:
    """Test MCP servers discovery endpoint integration."""
    
    @pytest.mark.integration
    def test_mcp_servers_endpoint_returns_servers_list(self, client: TestClient) -> None:
        """Test endpoint returns list of available MCP servers and their tools."""
        # Mock MCP client and server registry
        with patch("tarsy.main.alert_service") as mock_alert_service:
            # Setup mock MCP client
            mock_mcp_client = AsyncMock()
            mock_mcp_client.list_tools.return_value = {
                "kubernetes-server": [
                    AsyncMock(
                        name="core_v1_list_pod",
                        description="List pods",
                        inputSchema={"type": "object", "properties": {}}
                    ),
                    AsyncMock(
                        name="core_v1_read_namespaced_pod",
                        description="Read pod details",
                        inputSchema={"type": "object", "properties": {}}
                    )
                ]
            }
            mock_mcp_client.cleanup = AsyncMock()
            
            # Setup mock client factory
            mock_client_factory = AsyncMock()
            mock_client_factory.create_client.return_value = mock_mcp_client
            mock_alert_service.mcp_client_factory = mock_client_factory
            
            # Setup mock server registry
            mock_server_registry = AsyncMock()
            mock_server_registry.get_all_server_ids.return_value = ["kubernetes-server"]
            
            # Mock server config
            mock_server_config = AsyncMock()
            mock_server_config.server_id = "kubernetes-server"
            mock_server_config.server_type = "kubernetes"
            mock_server_config.enabled = True
            mock_server_registry.get_server_config.return_value = mock_server_config
            
            mock_alert_service.mcp_server_registry = mock_server_registry
            
            response = client.get("/api/v1/system/mcp-servers")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "servers" in data
        assert "total_servers" in data
        assert "total_tools" in data
        
        assert len(data["servers"]) == 1
        assert data["servers"][0]["server_id"] == "kubernetes-server"
        assert data["servers"][0]["server_type"] == "kubernetes"
        assert data["servers"][0]["enabled"] is True
        assert len(data["servers"][0]["tools"]) == 2
        
        assert data["total_servers"] == 1
        assert data["total_tools"] == 2
    
    @pytest.mark.integration
    def test_mcp_servers_endpoint_handles_server_errors_gracefully(
        self, client: TestClient
    ) -> None:
        """Test endpoint handles server errors without failing completely."""
        with patch("tarsy.main.alert_service") as mock_alert_service:
            mock_mcp_client = AsyncMock()
            # First server fails, should continue with others
            mock_mcp_client.list_tools.side_effect = Exception("Server connection failed")
            mock_mcp_client.cleanup = AsyncMock()
            
            mock_client_factory = AsyncMock()
            mock_client_factory.create_client.return_value = mock_mcp_client
            mock_alert_service.mcp_client_factory = mock_client_factory
            
            mock_server_registry = AsyncMock()
            mock_server_registry.get_all_server_ids.return_value = ["kubernetes-server"]
            
            mock_server_config = AsyncMock()
            mock_server_config.server_id = "kubernetes-server"
            mock_server_config.server_type = "kubernetes"
            mock_server_config.enabled = True
            mock_server_registry.get_server_config.return_value = mock_server_config
            
            mock_alert_service.mcp_server_registry = mock_server_registry
            
            response = client.get("/api/v1/system/mcp-servers")
        
        # Should still return 200 with server included but no tools
        assert response.status_code == 200
        data = response.json()
        assert len(data["servers"]) == 1
        assert data["servers"][0]["tools"] == []


class TestAlertSubmissionWithMCPSelection:
    """Test alert submission with MCP selection integration."""
    
    @pytest.mark.integration
    def test_alert_submission_accepts_mcp_server_selection(
        self, client: TestClient
    ) -> None:
        """Test submitting alert with MCP server selection (all tools)."""
        alert_data = {
            "alert_type": "PodCrashLoop",
            "data": {
                "pod_name": "test-pod",
                "namespace": "default"
            },
            "mcp": {
                "servers": [
                    {"name": "kubernetes-server"}
                ]
            }
        }
        
        # Mock the background processing to avoid actual execution
        with patch("tarsy.controllers.alert_controller.asyncio.create_task") as mock_task:
            mock_task.return_value = AsyncMock()
            
            response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "queued"
    
    @pytest.mark.integration
    def test_alert_submission_accepts_mcp_tool_selection(
        self, client: TestClient
    ) -> None:
        """Test submitting alert with specific tool selection."""
        alert_data = {
            "alert_type": "PodCrashLoop",
            "data": {
                "pod_name": "test-pod",
                "namespace": "default"
            },
            "mcp": {
                "servers": [
                    {
                        "name": "kubernetes-server",
                        "tools": ["core_v1_list_pod", "core_v1_read_namespaced_pod"]
                    }
                ]
            }
        }
        
        with patch("tarsy.controllers.alert_controller.asyncio.create_task") as mock_task:
            mock_task.return_value = AsyncMock()
            
            response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "queued"
    
    @pytest.mark.integration
    def test_alert_submission_accepts_mixed_mcp_selection(
        self, client: TestClient
    ) -> None:
        """Test submitting alert with mix of all-tools and specific-tools servers."""
        alert_data = {
            "alert_type": "PodCrashLoop",
            "data": {
                "pod_name": "test-pod",
                "namespace": "default"
            },
            "mcp": {
                "servers": [
                    {"name": "kubernetes-server"},  # All tools
                    {
                        "name": "argocd-server",
                        "tools": ["get_application"]  # Specific tools
                    }
                ]
            }
        }
        
        with patch("tarsy.controllers.alert_controller.asyncio.create_task") as mock_task:
            mock_task.return_value = AsyncMock()
            
            response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
    
    @pytest.mark.integration
    def test_alert_submission_without_mcp_selection_still_works(
        self, client: TestClient
    ) -> None:
        """Test alert submission without MCP selection works (backward compatibility)."""
        alert_data = {
            "alert_type": "PodCrashLoop",
            "data": {
                "pod_name": "test-pod",
                "namespace": "default"
            }
        }
        
        with patch("tarsy.controllers.alert_controller.asyncio.create_task") as mock_task:
            mock_task.return_value = AsyncMock()
            
            response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "queued"
    
    @pytest.mark.integration
    def test_alert_submission_rejects_empty_servers_list(
        self, client: TestClient
    ) -> None:
        """Test alert submission rejects MCP selection with empty servers list."""
        alert_data = {
            "alert_type": "PodCrashLoop",
            "data": {
                "pod_name": "test-pod",
                "namespace": "default"
            },
            "mcp": {
                "servers": []  # Empty list should be rejected
            }
        }
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.integration
    def test_alert_submission_rejects_server_without_name(
        self, client: TestClient
    ) -> None:
        """Test alert submission rejects server selection without name."""
        alert_data = {
            "alert_type": "PodCrashLoop",
            "data": {
                "pod_name": "test-pod",
                "namespace": "default"
            },
            "mcp": {
                "servers": [
                    {"tools": ["some_tool"]}  # Missing name field
                ]
            }
        }
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

