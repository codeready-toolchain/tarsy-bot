"""Integration tests for MCP health monitoring."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import Tool

from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.system_models import WarningCategory
from tarsy.services.mcp_health_monitor import MCPHealthMonitor
from tarsy.services.system_warnings_service import SystemWarningsService


@pytest.fixture
def warnings_service() -> SystemWarningsService:
    """Create a fresh warnings service instance for each test."""
    # Get singleton but clear it for test isolation
    service = SystemWarningsService.get_instance()
    service._warnings.clear()
    return service


def _create_mock_tools_result(tools_count: int = 1):
    """Helper to create a mock list_tools result."""
    tools = [Tool(name=f"tool-{i}", description=f"Test tool {i}", inputSchema={}) 
             for i in range(tools_count)]
    result = MagicMock()
    result.tools = tools
    return result


@pytest.fixture
def mock_mcp_client() -> MagicMock:
    """Create a mock MCP client for integration tests."""
    client = MagicMock(spec=MCPClient)
    client.mcp_registry = MagicMock()
    client.mcp_registry.get_all_server_ids.return_value = ["test-server-1", "test-server-2"]
    client.sessions = {}
    client.try_initialize_server = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_health_monitor_startup_and_shutdown(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test health monitor can start and stop cleanly."""
    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    assert monitor._running is True
    
    await asyncio.sleep(0.05)  # Let it run briefly
    
    await monitor.stop()
    assert monitor._running is False


@pytest.mark.asyncio
async def test_health_monitor_detects_unhealthy_server(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test that health monitor detects and reports unhealthy servers."""
    # Setup: server exists but list_tools fails (unhealthy)
    mock_session = AsyncMock()
    mock_session.list_tools.side_effect = Exception("Connection failed")
    mock_mcp_client.sessions = {"test-server-1": mock_session}
    mock_mcp_client.mcp_registry.get_server_config_safe.return_value = MagicMock(enabled=True)

    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    await asyncio.sleep(0.25)  # Wait for at least one check cycle
    await monitor.stop()

    # Verify warning was added
    warnings = warnings_service.get_warnings()
    assert len(warnings) >= 1
    mcp_warnings = [
        w for w in warnings if w.category == WarningCategory.MCP_INITIALIZATION
    ]
    assert len(mcp_warnings) >= 1
    assert mcp_warnings[0].server_id == "test-server-1"


@pytest.mark.asyncio
async def test_health_monitor_clears_warning_on_recovery(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test that health monitor clears warnings when server recovers."""
    # Setup: Start with unhealthy server (list_tools fails)
    mock_session = AsyncMock()
    mock_session.list_tools.side_effect = Exception("Connection failed")
    mock_mcp_client.sessions = {"test-server-1": mock_session}
    mock_mcp_client.mcp_registry.get_server_config_safe.return_value = MagicMock(enabled=True)

    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    await asyncio.sleep(0.25)  # Wait for unhealthy detection
    
    # Verify warning exists
    warnings = warnings_service.get_warnings()
    assert len([w for w in warnings if w.category == WarningCategory.MCP_INITIALIZATION]) >= 1

    # Now server recovers (list_tools succeeds)
    mock_session.list_tools.side_effect = None
    mock_session.list_tools.return_value = _create_mock_tools_result()
    await asyncio.sleep(0.25)  # Wait for health check to clear warning
    
    await monitor.stop()

    # Verify warning was cleared
    warnings = warnings_service.get_warnings()
    mcp_warnings = [
        w for w in warnings 
        if w.category == WarningCategory.MCP_INITIALIZATION and w.server_id == "test-server-1"
    ]
    assert len(mcp_warnings) == 0


@pytest.mark.asyncio
async def test_health_monitor_initializes_failed_startup_server(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test that health monitor attempts to initialize servers that failed at startup."""
    # Setup: server has no session (failed at startup)
    mock_mcp_client.sessions = {}
    mock_mcp_client.mcp_registry.get_server_config_safe.return_value = MagicMock(enabled=True)
    mock_mcp_client.try_initialize_server.return_value = True

    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    await asyncio.sleep(0.25)  # Wait for at least one check cycle
    await monitor.stop()

    # Verify try_initialize_server was called
    assert mock_mcp_client.try_initialize_server.call_count >= 1
    mock_mcp_client.try_initialize_server.assert_any_call("test-server-1")


@pytest.mark.asyncio
async def test_health_monitor_handles_multiple_servers(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test health monitor handles multiple servers with different states."""
    # Setup: server-1 healthy, server-2 unhealthy
    mock_session1 = AsyncMock()
    mock_session1.list_tools.return_value = _create_mock_tools_result()
    
    mock_session2 = AsyncMock()
    mock_session2.list_tools.side_effect = Exception("Connection failed")
    
    mock_mcp_client.sessions = {
        "test-server-1": mock_session1,
        "test-server-2": mock_session2,
    }
    mock_mcp_client.mcp_registry.get_server_config_safe.return_value = MagicMock(enabled=True)

    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    await asyncio.sleep(0.25)  # Wait for at least one check cycle
    await monitor.stop()

    # Verify only server-2 has warning
    warnings = warnings_service.get_warnings()
    mcp_warnings = [
        w for w in warnings if w.category == WarningCategory.MCP_INITIALIZATION
    ]
    
    # Should have exactly one warning for server-2
    server_2_warnings = [w for w in mcp_warnings if w.server_id == "test-server-2"]
    assert len(server_2_warnings) >= 1
    
    # Should not have warning for server-1
    server_1_warnings = [w for w in mcp_warnings if w.server_id == "test-server-1"]
    assert len(server_1_warnings) == 0


@pytest.mark.asyncio
async def test_health_monitor_continues_after_check_error(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test that health monitor continues running even if individual checks fail."""
    call_count = 0
    
    async def list_tools_with_intermittent_error():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Simulated check error")
        return _create_mock_tools_result()
    
    mock_session = AsyncMock()
    mock_session.list_tools.side_effect = list_tools_with_intermittent_error
    mock_mcp_client.sessions = {"test-server-1": mock_session}
    mock_mcp_client.mcp_registry.get_server_config_safe.return_value = MagicMock(enabled=True)

    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    await asyncio.sleep(0.35)  # Wait for multiple check cycles
    await monitor.stop()

    # Should have attempted multiple checks despite first error
    assert call_count >= 2


@pytest.mark.asyncio
async def test_health_monitor_does_not_duplicate_warnings(
    mock_mcp_client: MagicMock,
    warnings_service: SystemWarningsService,
) -> None:
    """Test that health monitor does not create duplicate warnings."""
    # Setup: unhealthy server (list_tools fails)
    mock_session = AsyncMock()
    mock_session.list_tools.side_effect = Exception("Connection failed")
    mock_mcp_client.sessions = {"test-server-1": mock_session}
    mock_mcp_client.mcp_registry.get_server_config_safe.return_value = MagicMock(enabled=True)

    monitor = MCPHealthMonitor(
        mcp_client=mock_mcp_client,
        warnings_service=warnings_service,
        check_interval=0.1,
    )

    await monitor.start()
    await asyncio.sleep(0.35)  # Wait for multiple check cycles
    await monitor.stop()

    # Should only have one warning even after multiple checks
    warnings = warnings_service.get_warnings()
    mcp_warnings = [
        w for w in warnings 
        if w.category == WarningCategory.MCP_INITIALIZATION and w.server_id == "test-server-1"
    ]
    assert len(mcp_warnings) == 1