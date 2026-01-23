"""
Integration tests for concurrent MCP transport operations.

This test validates the fix for the cancel scope mismatch bug that occurred
when multiple MCP transports were created, used, and closed concurrently.

The original issue: RuntimeError "Attempted to exit a cancel scope that isn't
the current task's current cancel scope" during concurrent transport cleanup.

These tests verify that:
1. Multiple MCP clients can be created and closed concurrently
2. Cancel scope errors during close are properly suppressed
3. The transport layer handles concurrent cleanup gracefully
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.integrations.mcp.transport.error_handling import (
    is_cancel_scope_mismatch_error,
    is_safe_teardown_error,
)
from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
from tarsy.services.mcp_server_registry import MCPServerRegistry


def create_mock_registry(server_ids: List[str]) -> Mock:
    """Create a mock MCP server registry with specified server IDs."""
    registry = Mock(spec=MCPServerRegistry)
    registry.get_all_server_ids.return_value = server_ids

    mock_transport = Mock()
    mock_transport.type = TRANSPORT_STDIO
    mock_transport.command = "echo"
    mock_transport.args = ["test"]
    mock_transport.env = {}

    registry.get_server_config_safe.return_value = Mock(
        enabled=True,
        transport=mock_transport,
    )
    return registry


def create_mock_transport(server_id: str) -> Mock:
    """Create a mock transport for a server."""
    mock_transport = Mock()
    mock_session = AsyncMock()

    # Mock list_tools with proper inputSchema
    mock_tools = [
        Tool(
            name=f"tool_{server_id}_1",
            description=f"Test tool 1 for {server_id}",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name=f"tool_{server_id}_2",
            description=f"Test tool 2 for {server_id}",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    mock_session.list_tools.return_value = Mock(tools=mock_tools)

    # Mock call_tool
    async def mock_call_tool(_name, _arguments):
        await asyncio.sleep(0.01)
        return Mock(content=[Mock(text=f"Result from {server_id}")])

    mock_session.call_tool = mock_call_tool

    mock_transport.create_session = AsyncMock(return_value=mock_session)
    mock_transport.is_connected = True
    mock_transport.close = AsyncMock()

    return mock_transport


@pytest.mark.integration
class TestMCPTransportConcurrency:
    """Integration tests for concurrent MCP transport operations."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for tests."""
        settings = Mock(spec=Settings)
        settings.agent_config_path = None
        return settings

    @pytest.mark.asyncio
    async def test_concurrent_client_close_no_cancel_scope_errors(self, mock_settings):
        """
        Test that concurrent client close operations don't cause cancel scope errors.

        This is the core test for the cancel scope mismatch bug fix.
        Multiple clients closing their transports concurrently should not
        cause RuntimeError about cancel scope mismatches.
        """
        num_clients = 4
        server_ids = ["server-1", "server-2"]

        close_errors: List[Exception] = []
        cancel_scope_errors: List[Exception] = []

        with patch(
            "tarsy.integrations.mcp.client.MCPTransportFactory"
        ) as mock_factory_cls:
            # Return a new mock transport for each call
            mock_factory_cls.create_transport.side_effect = (
                lambda _c, sid, _e: create_mock_transport(sid)
            )

            # Initialize clients
            clients = []
            for _ in range(num_clients):
                registry = create_mock_registry(server_ids)
                client = MCPClient(mock_settings, registry)
                await client.initialize()
                clients.append(client)

            # Verify all clients initialized
            for client in clients:
                assert client._initialized is True

            # Close all clients concurrently
            async def close_client(client: MCPClient):
                try:
                    await client.close()
                except Exception as e:
                    close_errors.append(e)
                    if is_cancel_scope_mismatch_error(e):
                        cancel_scope_errors.append(e)

            await asyncio.gather(*[close_client(c) for c in clients])

        # The key assertion: no cancel scope mismatch errors
        assert len(cancel_scope_errors) == 0, (
            f"Cancel scope mismatch errors occurred during concurrent close: "
            f"{[str(e) for e in cancel_scope_errors]}"
        )

        # Also verify no other unexpected errors
        assert len(close_errors) == 0, (
            f"Unexpected errors during concurrent close: "
            f"{[str(e) for e in close_errors]}"
        )

    @pytest.mark.asyncio
    async def test_interleaved_init_and_close_operations(self, mock_settings):
        """
        Test interleaved initialization and close operations.

        Simulates a realistic scenario where some clients are being created
        while others are being closed (e.g., during session turnover).
        """
        server_ids = ["server-1"]
        errors: List[Exception] = []

        with patch(
            "tarsy.integrations.mcp.client.MCPTransportFactory"
        ) as mock_factory_cls:
            mock_factory_cls.create_transport.side_effect = (
                lambda _c, sid, _e: create_mock_transport(sid)
            )

            async def create_use_and_close():
                """Create a client, use it briefly, then close it."""
                try:
                    registry = create_mock_registry(server_ids)
                    client = MCPClient(mock_settings, registry)
                    await client.initialize()

                    # Brief usage - list_tools returns dict {server_id: [tools]}
                    tools_dict = await client.list_tools("server-1")
                    assert "server-1" in tools_dict

                    await asyncio.sleep(0.01)

                    # Close
                    await client.close()
                except Exception as e:
                    errors.append(e)

            # Run multiple interleaved operations with staggered starts
            tasks = []
            for _ in range(6):
                # Stagger the start times slightly
                await asyncio.sleep(0.005)
                tasks.append(asyncio.create_task(create_use_and_close()))

            await asyncio.gather(*tasks)

        # No errors should have occurred
        assert len(errors) == 0, f"Errors during interleaved operations: {errors}"

    @pytest.mark.asyncio
    async def test_rapid_sequential_client_lifecycle(self, mock_settings):
        """
        Test rapid sequential client creation and destruction.

        This tests that resources are properly cleaned up between
        client lifecycles without accumulating state issues.
        """
        server_ids = ["server-1"]
        lifecycle_count = 10

        with patch(
            "tarsy.integrations.mcp.client.MCPTransportFactory"
        ) as mock_factory_cls:
            mock_factory_cls.create_transport.side_effect = (
                lambda _c, sid, _e: create_mock_transport(sid)
            )

            for _ in range(lifecycle_count):
                registry = create_mock_registry(server_ids)
                client = MCPClient(mock_settings, registry)

                await client.initialize()
                assert client._initialized is True

                # list_tools returns dict {server_id: [tools]}
                tools_dict = await client.list_tools("server-1")
                assert "server-1" in tools_dict
                assert len(tools_dict["server-1"]) == 2

                await client.close()
                # After close, sessions should be cleared
                assert len(client.sessions) == 0


@pytest.mark.integration
class TestCancelScopeErrorHandling:
    """Tests for cancel scope error detection and handling."""

    def test_cancel_scope_error_detection(self):
        """Test the is_cancel_scope_mismatch_error utility function."""
        # Should detect the specific error
        error1 = RuntimeError(
            "Attempted to exit cancel scope in a different task than it was entered in"
        )
        assert is_cancel_scope_mismatch_error(error1) is True

        # Should not match other RuntimeErrors
        error2 = RuntimeError("Some other error")
        assert is_cancel_scope_mismatch_error(error2) is False

        # Should not match non-RuntimeErrors
        error3 = ValueError("Attempted to exit cancel scope")
        assert is_cancel_scope_mismatch_error(error3) is False

    def test_safe_teardown_error_detection(self):
        """Test is_safe_teardown_error for various error types."""
        # Cancel scope mismatch should be safe
        error1 = RuntimeError(
            "Attempted to exit cancel scope in a different task than it was entered in"
        )
        assert is_safe_teardown_error(error1) is True

        # GeneratorExit should be safe
        assert is_safe_teardown_error(GeneratorExit()) is True

        # Regular errors should not be safe
        assert is_safe_teardown_error(ValueError("error")) is False
        assert is_safe_teardown_error(RuntimeError("other error")) is False

    @pytest.mark.asyncio
    async def test_client_close_suppresses_transport_errors(self):
        """
        Test that MCPClient.close() gracefully handles transport errors.

        The client's close method catches and logs transport errors
        rather than propagating them.
        """
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None

        # Create a transport that raises error on close
        def create_problematic_transport(_c, server_id, _e):
            transport = create_mock_transport(server_id)

            async def raise_error():
                raise RuntimeError(
                    "Attempted to exit cancel scope in a different task "
                    "than it was entered in"
                )

            transport.close = raise_error
            return transport

        with patch(
            "tarsy.integrations.mcp.client.MCPTransportFactory"
        ) as mock_factory_cls:
            mock_factory_cls.create_transport.side_effect = create_problematic_transport

            registry = create_mock_registry(["server-1"])
            client = MCPClient(mock_settings, registry)
            await client.initialize()

            # Close should NOT raise - the client catches transport errors
            # and logs them instead of propagating
            await client.close()

            # Verify client state is cleaned up
            assert len(client.sessions) == 0
