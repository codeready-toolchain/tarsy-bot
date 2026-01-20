"""Unit tests for MCPHealthMonitor service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import Tool

from tarsy.models.system_models import WarningCategory
from tarsy.services.mcp_health_monitor import MCPHealthMonitor, _mcp_warning_message


class TestMCPHealthMonitor:
    """Test suite for MCPHealthMonitor service."""

    @pytest.fixture
    def mock_mcp_client(self) -> MagicMock:
        """Create a mock MCP client."""
        client = MagicMock()
        client.mcp_registry = MagicMock()
        client.mcp_registry.get_all_server_ids.return_value = ["server1", "server2"]
        client.sessions = {}
        client.ping = AsyncMock()
        client.try_initialize_server = AsyncMock()
        return client

    @pytest.fixture
    def mock_warnings_service(self) -> MagicMock:
        """Create a mock warnings service."""
        service = MagicMock()
        service.get_warnings.return_value = []
        service.add_warning.return_value = "warning-id-123"
        service.clear_warning_by_server_id.return_value = True
        return service

    @pytest.fixture
    def health_monitor(
        self, mock_mcp_client: MagicMock, mock_warnings_service: MagicMock
    ) -> MCPHealthMonitor:
        """Create a health monitor instance."""
        return MCPHealthMonitor(
            mcp_client=mock_mcp_client,
            warnings_service=mock_warnings_service,
            check_interval=0.1,  # Short interval for tests
        )

    @pytest.mark.asyncio
    async def test_start_monitor(self, health_monitor: MCPHealthMonitor) -> None:
        """Test starting the health monitor."""
        await health_monitor.start()
        assert health_monitor._running is True
        assert health_monitor._monitor_task is not None
        await health_monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_monitor(self, health_monitor: MCPHealthMonitor) -> None:
        """Test stopping the health monitor."""
        await health_monitor.start()
        await health_monitor.stop()
        assert health_monitor._running is False

    @pytest.mark.asyncio
    async def test_start_already_running(
        self, health_monitor: MCPHealthMonitor
    ) -> None:
        """Test starting monitor when already running logs warning."""
        await health_monitor.start()
        # Start again - should log warning but not fail
        await health_monitor.start()
        await health_monitor.stop()

    @pytest.mark.asyncio
    async def test_check_server_missing_config(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test checking a server with missing config - should skip checks and clear warnings."""
        # Mock missing config (returns None)
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = None

        is_healthy = await health_monitor._check_server("missing_server")

        # Returns True to indicate "no warning needed" (not that server is healthy)
        assert is_healthy is True
        # Should not attempt to ping or initialize
        mock_mcp_client.ping.assert_not_called()
        mock_mcp_client.try_initialize_server.assert_not_called()
        # Should clear any stale warnings
        mock_warnings_service.clear_warning_by_server_id.assert_called_once_with(
            category=WarningCategory.MCP_INITIALIZATION,
            server_id="missing_server",
        )

    @pytest.mark.asyncio
    async def test_check_server_with_session_healthy(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
    ) -> None:
        """Test checking a server that has a session and is healthy."""
        # Mock an enabled server config
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        
        # Mock session with successful list_tools
        mock_session = AsyncMock()
        test_tools = [Tool(name="test-tool", description="Test", inputSchema={})]
        mock_tools_result = MagicMock()
        mock_tools_result.tools = test_tools
        mock_session.list_tools.return_value = mock_tools_result
        mock_mcp_client.sessions = {"server1": mock_session}

        is_healthy = await health_monitor._check_server("server1")

        assert is_healthy is True
        # Should have called list_tools once (not ping separately)
        mock_session.list_tools.assert_called_once()
        mock_mcp_client.try_initialize_server.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_server_with_session_unhealthy(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
    ) -> None:
        """Test checking a server that has a session but ping fails and recovery fails."""
        # Mock an enabled server config
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        
        # Mock session with failed list_tools
        mock_session = AsyncMock()
        mock_session.list_tools.side_effect = Exception("Connection failed")
        mock_mcp_client.sessions = {"server1": mock_session}
        mock_mcp_client.try_initialize_server.return_value = False

        is_healthy = await health_monitor._check_server("server1")

        assert is_healthy is False
        # Should have called list_tools once (ping failed)
        mock_session.list_tools.assert_called_once()
        # Recovery is attempted after ping fails
        mock_mcp_client.try_initialize_server.assert_called_once_with("server1")

    @pytest.mark.asyncio
    async def test_check_server_no_session_init_success(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
    ) -> None:
        """Test checking a server with no session - initialization succeeds and ping verifies."""
        # Mock an enabled server config
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        mock_mcp_client.sessions = {}
        mock_mcp_client.try_initialize_server.return_value = True
        
        # After init, mock the session with successful list_tools
        mock_session = AsyncMock()
        test_tools = [Tool(name="test-tool", description="Test", inputSchema={})]
        mock_tools_result = MagicMock()
        mock_tools_result.tools = test_tools
        mock_session.list_tools.return_value = mock_tools_result
        
        # Simulate session being created after init
        async def add_session_after_init(server_id):
            mock_mcp_client.sessions[server_id] = mock_session
            return True
        mock_mcp_client.try_initialize_server.side_effect = add_session_after_init

        is_healthy = await health_monitor._check_server("server1")

        assert is_healthy is True
        mock_mcp_client.try_initialize_server.assert_called_once_with("server1")
        # After successful init, we ping/cache tools to verify the session works
        mock_session.list_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_server_no_session_init_failure(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
    ) -> None:
        """Test checking a server with no session - initialization fails."""
        # Mock an enabled server config
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        mock_mcp_client.sessions = {}
        mock_mcp_client.try_initialize_server.return_value = False

        is_healthy = await health_monitor._check_server("server1")

        assert is_healthy is False
        mock_mcp_client.try_initialize_server.assert_called_once_with("server1")

    @pytest.mark.asyncio
    async def test_ensure_warning_adds_warning(
        self,
        health_monitor: MCPHealthMonitor,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test that ensure_warning adds a warning when none exists."""
        mock_warnings_service.get_warnings.return_value = []

        health_monitor._ensure_warning("server1")

        mock_warnings_service.add_warning.assert_called_once()
        call_args = mock_warnings_service.add_warning.call_args[1]
        assert call_args["category"] == WarningCategory.MCP_INITIALIZATION
        assert call_args["server_id"] == "server1"
        assert call_args["message"] == _mcp_warning_message("server1")

    @pytest.mark.asyncio
    async def test_ensure_warning_does_not_duplicate(
        self,
        health_monitor: MCPHealthMonitor,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test that ensure_warning does not add duplicate warnings."""
        # Mock existing warning for server1
        existing_warning = MagicMock()
        existing_warning.category = WarningCategory.MCP_INITIALIZATION
        existing_warning.server_id = "server1"
        mock_warnings_service.get_warnings.return_value = [existing_warning]

        health_monitor._ensure_warning("server1")

        # Should not add a new warning
        mock_warnings_service.add_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_warning(
        self,
        health_monitor: MCPHealthMonitor,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test clearing a warning."""
        mock_warnings_service.clear_warning_by_server_id.return_value = True

        health_monitor._clear_warning("server1")

        mock_warnings_service.clear_warning_by_server_id.assert_called_once_with(
            category=WarningCategory.MCP_INITIALIZATION,
            server_id="server1",
        )

    @pytest.mark.asyncio
    async def test_clear_warning_none_exists(
        self,
        health_monitor: MCPHealthMonitor,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test clearing a warning when none exists."""
        mock_warnings_service.clear_warning_by_server_id.return_value = False

        # Should not raise an error
        health_monitor._clear_warning("server1")

        mock_warnings_service.clear_warning_by_server_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_all_servers_healthy(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test checking all servers when they are all healthy."""
        # Mock enabled server configs
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        
        # Mock sessions with successful list_tools
        mock_session1 = AsyncMock()
        mock_session2 = AsyncMock()
        test_tools = [Tool(name="test-tool", description="Test", inputSchema={})]
        mock_tools_result = MagicMock()
        mock_tools_result.tools = test_tools
        mock_session1.list_tools.return_value = mock_tools_result
        mock_session2.list_tools.return_value = mock_tools_result
        mock_mcp_client.sessions = {"server1": mock_session1, "server2": mock_session2}

        await health_monitor._check_all_servers()

        # Both servers should have list_tools called (ping+cache)
        mock_session1.list_tools.assert_called_once()
        mock_session2.list_tools.assert_called_once()
        # Warnings should be cleared for both
        assert mock_warnings_service.clear_warning_by_server_id.call_count == 2

    @pytest.mark.asyncio
    async def test_check_all_servers_mixed_health(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
        mock_warnings_service: MagicMock,
    ) -> None:
        """Test checking all servers with mixed health states."""
        # Mock enabled server configs
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        
        # Mock session for server1 (healthy)
        mock_session1 = AsyncMock()
        test_tools = [Tool(name="test-tool", description="Test", inputSchema={})]
        mock_tools_result = MagicMock()
        mock_tools_result.tools = test_tools
        mock_session1.list_tools.return_value = mock_tools_result
        mock_mcp_client.sessions = {"server1": mock_session1}
        
        # server1 healthy, server2 has no session and init fails
        mock_mcp_client.try_initialize_server.return_value = False
        mock_warnings_service.get_warnings.return_value = []

        await health_monitor._check_all_servers()

        # server1 should have warning cleared
        # server2 should have warning added
        assert mock_warnings_service.clear_warning_by_server_id.call_count == 1
        assert mock_warnings_service.add_warning.call_count == 1

    @pytest.mark.asyncio
    async def test_monitor_loop_continues_on_error(
        self,
        health_monitor: MCPHealthMonitor,
        mock_mcp_client: MagicMock,
    ) -> None:
        """Test that monitor loop continues even if check_all_servers raises error."""
        call_count = 0

        async def check_with_error() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
            # After first error, stop the monitor
            health_monitor._running = False

        with patch.object(
            health_monitor,
            "_check_all_servers",
            new_callable=AsyncMock,
            side_effect=check_with_error,
        ):
            await health_monitor.start()
            # Give it time to run a couple iterations
            await asyncio.sleep(0.3)
            await health_monitor.stop()

        # Should have been called at least once (and continued after error)
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_mcp_warning_message_format(self) -> None:
        """Test the warning message format."""
        message = _mcp_warning_message("test-server")
        assert "test-server" in message
        assert "unreachable" in message.lower()
    
    @pytest.mark.asyncio
    async def test_get_cached_tools_empty(self, health_monitor: MCPHealthMonitor) -> None:
        """Test get_cached_tools returns empty dict initially."""
        cached_tools = health_monitor.get_cached_tools()
        assert cached_tools == {}
    
    @pytest.mark.asyncio
    async def test_get_cached_tools_returns_copy(
        self, health_monitor: MCPHealthMonitor
    ) -> None:
        """Test get_cached_tools returns a copy, not the original dict."""
        # Add something to internal cache
        test_tool = Tool(name="test-tool", description="Test", inputSchema={})
        health_monitor._tool_cache["server1"] = [test_tool]
        
        # Get cached tools and modify it
        cached_tools = health_monitor.get_cached_tools()
        cached_tools["server2"] = []
        
        # Original cache should not be modified
        assert "server2" not in health_monitor._tool_cache
        assert "server1" in health_monitor._tool_cache
    
    @pytest.mark.asyncio
    async def test_get_cached_tools_returns_list_copies(
        self, health_monitor: MCPHealthMonitor
    ) -> None:
        """Test get_cached_tools returns defensive copies - modifying lists doesn't affect cache."""
        # Add tools to internal cache
        tool1 = Tool(name="tool-1", description="Tool 1", inputSchema={})
        tool2 = Tool(name="tool-2", description="Tool 2", inputSchema={})
        health_monitor._tool_cache["server1"] = [tool1, tool2]
        
        # Get cached tools and modify the list
        cached_tools = health_monitor.get_cached_tools()
        fake_tool = Tool(name="fake-tool", description="Fake", inputSchema={})
        cached_tools["server1"].append(fake_tool)
        
        # Original cache's list should not be modified
        assert len(health_monitor._tool_cache["server1"]) == 2
        assert fake_tool not in health_monitor._tool_cache["server1"]
        # But the returned copy should have the modification
        assert len(cached_tools["server1"]) == 3
        assert fake_tool in cached_tools["server1"]
    
    @pytest.mark.asyncio
    async def test_ping_and_cache_tools_success(
        self, health_monitor: MCPHealthMonitor, mock_mcp_client: MagicMock
    ) -> None:
        """Test successfully pinging and caching tools from a server."""
        # Mock session with list_tools
        mock_session = AsyncMock()
        test_tools = [
            Tool(name="tool1", description="Tool 1", inputSchema={}),
            Tool(name="tool2", description="Tool 2", inputSchema={})
        ]
        mock_tools_result = MagicMock()
        mock_tools_result.tools = test_tools
        mock_session.list_tools.return_value = mock_tools_result
        
        mock_mcp_client.sessions = {"server1": mock_session}
        
        # Ping and cache tools
        is_healthy = await health_monitor._ping_and_cache_tools("server1")
        
        # Verify server is healthy
        assert is_healthy is True
        
        # Verify tools are cached
        cached_tools = health_monitor.get_cached_tools()
        assert "server1" in cached_tools
        assert len(cached_tools["server1"]) == 2
        assert cached_tools["server1"][0].name == "tool1"
        assert cached_tools["server1"][1].name == "tool2"
    
    @pytest.mark.asyncio
    async def test_ping_and_cache_tools_no_session(
        self, health_monitor: MCPHealthMonitor, mock_mcp_client: MagicMock
    ) -> None:
        """Test ping and cache when server has no session."""
        mock_mcp_client.sessions = {}
        
        # Should return False
        is_healthy = await health_monitor._ping_and_cache_tools("server1")
        
        assert is_healthy is False
        
        # Cache should remain empty
        cached_tools = health_monitor.get_cached_tools()
        assert "server1" not in cached_tools
    
    @pytest.mark.asyncio
    async def test_ping_and_cache_tools_timeout(
        self, health_monitor: MCPHealthMonitor, mock_mcp_client: MagicMock
    ) -> None:
        """Test ping and cache when list_tools times out."""
        # Mock session that times out
        mock_session = AsyncMock()
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        mock_mcp_client.sessions = {"server1": mock_session}
        
        # Should return False
        is_healthy = await health_monitor._ping_and_cache_tools("server1")
        
        assert is_healthy is False
        
        # Cache should remain empty for this server
        cached_tools = health_monitor.get_cached_tools()
        assert "server1" not in cached_tools
    
    @pytest.mark.asyncio
    async def test_check_server_caches_tools_on_success(
        self, health_monitor: MCPHealthMonitor, mock_mcp_client: MagicMock
    ) -> None:
        """Test that checking a healthy server also caches its tools."""
        # Mock enabled server config
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        
        # Mock session with successful ping and list_tools
        mock_session = AsyncMock()
        test_tools = [Tool(name="test-tool", description="Test", inputSchema={})]
        mock_tools_result = MagicMock()
        mock_tools_result.tools = test_tools
        mock_session.list_tools.return_value = mock_tools_result
        
        mock_mcp_client.sessions = {"server1": mock_session}
        mock_mcp_client.ping.return_value = True
        
        # Check server
        is_healthy = await health_monitor._check_server("server1")
        
        assert is_healthy is True
        
        # Verify tools were cached
        cached_tools = health_monitor.get_cached_tools()
        assert "server1" in cached_tools
        assert len(cached_tools["server1"]) == 1
        assert cached_tools["server1"][0].name == "test-tool"
    
    @pytest.mark.asyncio
    async def test_check_server_retains_cache_on_failure(
        self, health_monitor: MCPHealthMonitor, mock_mcp_client: MagicMock
    ) -> None:
        """Test that cache is retained even when server becomes unhealthy."""
        # Pre-populate cache with tools
        test_tool = Tool(name="test-tool", description="Test", inputSchema={})
        health_monitor._tool_cache["server1"] = [test_tool]
        
        # Mock enabled server config
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_mcp_client.mcp_registry.get_server_config_safe.return_value = mock_config
        
        # Mock unhealthy server (ping fails, recovery fails)
        mock_mcp_client.sessions = {"server1": MagicMock()}
        mock_mcp_client.ping.return_value = False
        mock_mcp_client.try_initialize_server.return_value = False
        
        # Check server
        is_healthy = await health_monitor._check_server("server1")
        
        assert is_healthy is False
        
        # Verify cache is still present (not cleared)
        cached_tools = health_monitor.get_cached_tools()
        assert "server1" in cached_tools
        assert len(cached_tools["server1"]) == 1

