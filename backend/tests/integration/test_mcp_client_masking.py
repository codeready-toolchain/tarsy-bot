"""
Integration tests for MCP client data masking functionality.

Tests focus on practical end-to-end scenarios:
- MCPClient and DataMaskingService integration
- Configuration flow from registry to masking
- Real masking behavior in call_tool responses
- Error handling in integrated scenarios
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.mcp_config import MCPServerConfig
from tarsy.models.masking_config import MaskingConfig, MaskingPattern
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPClientMaskingIntegration:
    """Test integration between MCPClient and data masking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        
        # Create server configs with different masking setups
        self.server_configs = {
            "masked-server": {
                "server_id": "masked-server",
                "server_type": "test",
                "enabled": True,
                "connection_params": {"command": "test", "args": []},
                "instructions": "Test server with masking enabled",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["basic"],
                    "patterns": ["certificate"]
                }
            },
            "kubernetes-server": {
                "server_id": "kubernetes-server",
                "server_type": "kubernetes",
                "enabled": True,
                "connection_params": {"command": "npx", "args": ["-y", "kubernetes-mcp-server@latest"]},
                "instructions": "Kubernetes MCP server with enhanced secret masking",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["kubernetes"],
                    "patterns": ["certificate", "token"]
                }
            },
            "unmasked-server": {
                "server_id": "unmasked-server",
                "server_type": "test",
                "enabled": True,
                "connection_params": {"command": "test", "args": []},
                "instructions": "Test server without masking"
                # No data_masking configuration
            },
            "disabled-masking-server": {
                "server_id": "disabled-masking-server",
                "server_type": "test",
                "enabled": True,
                "connection_params": {"command": "test", "args": []},
                "instructions": "Test server with disabled masking",
                "data_masking": {
                    "enabled": False,
                    "pattern_groups": ["basic"]
                }
            }
        }
        
        # Create registry with test servers
        self.registry = MCPServerRegistry(config=self.server_configs)
        
        # Create MCP client with registry
        self.client = MCPClient(self.mock_settings, mcp_registry=self.registry)
        self.client._initialized = True
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_with_masking_enabled(self, mock_hook_context):
        """Test call_tool with masking enabled masks sensitive data."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="test-request-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock session with response containing sensitive data
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = "API response with api_key: sk_123456789012345678901234567890"
        mock_session.call_tool.return_value = mock_result
        self.client.sessions = {"masked-server": mock_session}
        
        # Call tool on server with masking enabled
        result = await self.client.call_tool(
            "masked-server", 
            "test-tool", 
            {"param": "value"}, 
            "test-session-123"
        )
        
        # Verify sensitive data is masked
        assert "sk_123456789012345678901234567890" not in str(result)
        assert "***MASKED_API_KEY***" in str(result)
        
        # Verify session was called
        mock_session.call_tool.assert_called_once_with("test-tool", {"param": "value"})
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_with_masking_disabled(self, mock_hook_context):
        """Test call_tool with masking disabled returns original data."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="test-request-124")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock session with sensitive data
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = "API response with api_key: sk_123456789012345678901234567890"
        mock_session.call_tool.return_value = mock_result
        self.client.sessions = {"disabled-masking-server": mock_session}
        
        # Call tool on server with masking disabled
        result = await self.client.call_tool(
            "disabled-masking-server",
            "test-tool", 
            {"param": "value"}, 
            "test-session-124"
        )
        
        # Verify sensitive data is NOT masked (masking disabled)
        assert "sk_123456789012345678901234567890" in str(result)
        assert "***MASKED_API_KEY***" not in str(result)
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_with_no_masking_config(self, mock_hook_context):
        """Test call_tool with no masking config returns original data."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="test-request-125")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock session
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = "API response with api_key: sk_123456789012345678901234567890"
        mock_session.call_tool.return_value = mock_result
        self.client.sessions = {"unmasked-server": mock_session}
        
        # Call tool on server without masking config
        result = await self.client.call_tool(
            "unmasked-server",
            "test-tool",
            {"param": "value"},
            "test-session-125"
        )
        
        # Verify no masking applied
        assert "sk_123456789012345678901234567890" in str(result)
        assert "***MASKED_API_KEY***" not in str(result)
    
    @patch('tarsy.integrations.mcp.client.HookContext') 
    async def test_call_tool_with_custom_patterns(self, mock_hook_context):
        """Test call_tool with custom masking patterns."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="test-request-126")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Create server with custom patterns
        custom_server_config = {
            "custom-server": {
                "server_id": "custom-server",
                "server_type": "test",
                "enabled": True,
                "connection_params": {"command": "test", "args": []},
                "instructions": "Test server with custom patterns",
                "data_masking": {
                    "enabled": True,
                    "custom_patterns": [
                        {
                            "name": "internal_id",
                            "pattern": r"internal_id_\d{6}",
                            "replacement": "***MASKED_INTERNAL_ID***",
                            "description": "Internal system IDs"
                        }
                    ]
                }
            }
        }
        
        # Create new client with custom config
        custom_registry = MCPServerRegistry(config=custom_server_config)
        custom_client = MCPClient(self.mock_settings, mcp_registry=custom_registry)
        custom_client._initialized = True
        
        # Setup mock session
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = "Process completed with internal_id_123456"
        mock_session.call_tool.return_value = mock_result
        custom_client.sessions = {"custom-server": mock_session}
        
        # Call tool
        result = await custom_client.call_tool(
            "custom-server",
            "test-tool",
            {"param": "value"},
            "test-session-126"
        )
        
        # Verify custom pattern masking
        assert "internal_id_123456" not in str(result)
        assert "***MASKED_INTERNAL_ID***" in str(result)
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_with_complex_response_structure(self, mock_hook_context):
        """Test masking works with complex nested response structures."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="test-request-127")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock session with complex response
        mock_session = AsyncMock()  
        mock_result = Mock()
        
        # Simulate MCP response with multiple content items
        mock_content_items = [
            Mock(text="First response part with api_key: sk_123456789012345678901234567890"),
            Mock(text="Second part with password: secretpass123")
        ]
        mock_result.content = mock_content_items
        mock_session.call_tool.return_value = mock_result
        self.client.sessions = {"masked-server": mock_session}
        
        # Call tool
        result = await self.client.call_tool(
            "masked-server",
            "complex-tool",
            {"param": "value"},
            "test-session-127"
        )
        
        # Verify both sensitive items are masked
        assert "sk_123456789012345678901234567890" not in str(result)
        assert "secretpass123" not in str(result)
        assert "***MASKED_API_KEY***" in str(result)
        assert "***MASKED_PASSWORD***" in str(result)
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_masking_error_handling(self, mock_hook_context):
        """Test that masking errors don't break the call_tool flow."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="test-request-128")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock session
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = "API response with sensitive data"
        mock_session.call_tool.return_value = mock_result
        self.client.sessions = {"masked-server": mock_session}
        
        # Mock the data masking service to raise an exception
        with patch.object(self.client.data_masking_service, 'mask_response') as mock_mask:
            mock_mask.side_effect = Exception("Masking service error")
            
            # Call should still succeed (error handled gracefully)
            result = await self.client.call_tool(
                "masked-server",
                "test-tool",
                {"param": "value"},
                "test-session-128"
            )
            
            # Should return original unmasked response when masking fails
            assert "API response with sensitive data" in str(result)
            assert result["result"] == "API response with sensitive data"

    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_kubernetes_secret_masking_integration(self, mock_hook_context):
        """Test complete Kubernetes secret masking integration."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="k8s-test-request-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Realistic Kubernetes secret response (matching user's example)
        k8s_secret_response = """apiVersion: v1
data:
  "password": "c3VwZXJzZWNyZXRwYXNzd29yZDEyMw=="
  username: YWRtaW4=
  api-key: YWJjZGVmZ2hpams12345
kind: Secret
metadata:
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"v1","kind":"Secret","metadata":{"annotations":{},"finalizers":["example.com/finalizer-name"],"name":"my-secret","namespace":"superman-dev"},"stringData":{"password": "supersecretpassword123","username":"admin","api-key":"abcdefghijk12345"},"type":"Opaque"}
  creationTimestamp: "2025-08-01T04:41:49Z"
  deletionGracePeriodSeconds: 0
  deletionTimestamp: "2025-08-01T04:42:04Z"
  finalizers:
  - example.com/finalizer-name
  name: my-secret
  namespace: superman-dev
  resourceVersion: "8071"
  uid: b4581053-1011-4c02-963d-0378c08bd1ce
type: Opaque"""
        
        # Setup mock session with Kubernetes secret response
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = k8s_secret_response
        mock_session.call_tool.return_value = mock_result
        
        self.client.sessions = {"kubernetes-server": mock_session}
        
        # Call kubernetes server (should use enhanced kubernetes pattern group)
        result = await self.client.call_tool(
            "kubernetes-server", "kubectl", {"args": ["get", "secret", "my-secret", "-o", "yaml"]}, "k8s-session"
        )
        
        # Expected complete masked result - entire secret with data section masked
        # Expected complete masked result (readable multi-line format)
        expected_yaml_content = """apiVersion: v1
data: ***MASKED_SECRET_DATA***
kind: Secret
metadata:
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"v1","kind":"Secret","metadata":{"annotations":{},"finalizers":["example.com/finalizer-name"],"name":"my-secret","namespace":"superman-dev"},"stringData":***MASKED_SECRET_DATA***,"type":"Opaque"}
  creationTimestamp: "2025-08-01T04:41:49Z"
  deletionGracePeriodSeconds: 0
  deletionTimestamp: "2025-08-01T04:42:04Z"
  finalizers:
  - example.com/finalizer-name
  name: my-secret
  namespace: superman-dev
  resourceVersion: "8071"
  uid: b4581053-1011-4c02-963d-0378c08bd1ce
type: Opaque"""
        
        # Assert the complete masked result
        assert result['result'] == expected_yaml_content
        
        print("✅ INTEGRATION TEST: Complete Kubernetes secret properly masked!")


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPClientMaskingConfigurationFlow:
    """Test configuration flow from registry to masking service."""
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_builtin_kubernetes_server_masking(self, mock_hook_context):
        """Test that built-in kubernetes server uses its masking configuration."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="k8s-request-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Use default registry (contains built-in kubernetes server with masking)
        mock_settings = Mock(spec=Settings)
        registry = MCPServerRegistry()  # Default built-in servers
        client = MCPClient(mock_settings, mcp_registry=registry)
        client._initialized = True
        
        # Setup mock session with Kubernetes-like response
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = '''
        {
          "data": {
            "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "certificate": "-----BEGIN CERTIFICATE-----\\nMIIBIjAN...\\n-----END CERTIFICATE-----"
          }
        }
        '''
        mock_session.call_tool.return_value = mock_result
        client.sessions = {"kubernetes-server": mock_session}
        
        # Call tool
        result = await client.call_tool(
            "kubernetes-server",
            "get-secret",
            {"namespace": "default", "name": "test-secret"},
            "k8s-session-123"
        )
        
        # Verify Kubernetes-specific masking patterns are applied
        result_str = str(result)
        # The kubernetes_secret pattern should mask the entire data block
        assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in result_str  # Token masked
        assert "MIIBIjAN" not in result_str  # Certificate masked  
        assert ("# All data section values have been masked for security" in result_str or 
                "***MASKED_TOKEN***" in result_str or 
                "***MASKED_CERTIFICATE***" in result_str)  # Some masking applied
    
    def test_masking_service_initialization_with_registry(self):
        """Test that DataMaskingService is properly initialized with registry."""
        mock_settings = Mock(spec=Settings)
        registry = MCPServerRegistry()
        client = MCPClient(mock_settings, mcp_registry=registry)
        
        # Verify masking service is initialized with registry
        assert client.data_masking_service is not None
        assert client.data_masking_service.mcp_registry is registry
        
        # Verify builtin patterns are loaded
        assert len(client.data_masking_service.compiled_patterns) > 0
        assert "api_key" in client.data_masking_service.compiled_patterns
        assert "password" in client.data_masking_service.compiled_patterns
    
    def test_masking_service_without_registry(self):
        """Test that DataMaskingService handles missing registry gracefully."""
        mock_settings = Mock(spec=Settings)
        client = MCPClient(mock_settings)  # No registry provided
        
        # Should still initialize but with no registry
        assert client.data_masking_service is None  # No registry = no masking service
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_different_servers_different_masking_configs(self, mock_hook_context):
        """Test that different servers use their own masking configurations."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="multi-server-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Create servers with different masking configs
        server_configs = {
            "basic-server": {
                "server_id": "basic-server",
                "server_type": "basic",
                "enabled": True,
                "connection_params": {"command": "basic", "args": []},
                "instructions": "Basic masking",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["basic"]  # Only api_key and password
                }
            },
            "security-server": {
                "server_id": "security-server", 
                "server_type": "security",
                "enabled": True,
                "connection_params": {"command": "security", "args": []},
                "instructions": "Security masking",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["security"]  # Includes certificate and token
                }
            }
        }
        
        mock_settings = Mock(spec=Settings)
        registry = MCPServerRegistry(config=server_configs)
        client = MCPClient(mock_settings, mcp_registry=registry)
        client._initialized = True
        
        # Test data with multiple sensitive items (use format that matches actual regex patterns)
        test_response = """config:
        api_key: sk_123456789012345678901234567890
        certificate: -----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890
-----END CERTIFICATE-----
        token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9123456789012345678901234567890"""
        
        # Setup sessions
        mock_basic_session = AsyncMock()
        mock_basic_result = Mock()
        mock_basic_result.content = test_response
        mock_basic_session.call_tool.return_value = mock_basic_result
        
        mock_security_session = AsyncMock()
        mock_security_result = Mock()
        mock_security_result.content = test_response
        mock_security_session.call_tool.return_value = mock_security_result
        
        client.sessions = {
            "basic-server": mock_basic_session,
            "security-server": mock_security_session
        }
        
        # Call basic server (should only mask basic patterns)
        basic_result = await client.call_tool(
            "basic-server", "test", {}, "session-basic"
        )
        
        # Call security server (should mask more patterns)
        security_result = await client.call_tool(
            "security-server", "test", {}, "session-security"
        )
        
        # Verify different masking behavior 
        basic_str = str(basic_result)
        security_str = str(security_result)
        
        # Both should mask API key (in basic group)
        assert "sk_123456789012345678901234567890" not in basic_str
        assert "sk_123456789012345678901234567890" not in security_str
        assert "***MASKED_API_KEY***" in basic_str  
        assert "***MASKED_API_KEY***" in security_str
        
        # Only security server should mask certificate and token
        assert "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890" in basic_str  # Not masked by basic
        assert "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890" not in security_str  # Masked by security
        assert "***MASKED_CERTIFICATE***" not in basic_str
        assert "***MASKED_CERTIFICATE***" in security_str

