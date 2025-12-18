"""
Unit tests for MCP client recovery behavior.

Focuses on retry-once logic for transient HTTP/transport failures and
non-retry behavior for JSON-RPC semantic errors.
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient


@pytest.mark.unit
class TestMCPClientRecovery:
    @pytest.fixture
    def client(self) -> MCPClient:
        settings = Mock(spec=Settings)
        registry = Mock()
        registry.get_server_config_safe.return_value = Mock(enabled=True)
        return MCPClient(settings, registry)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,should_reinit,should_retry",
        [
            (404, True, True),
            (502, True, True),
            (503, True, True),
            (504, True, True),
            (500, True, True),
            (400, False, False),
            (401, False, False),
            (403, False, False),
        ],
    )
    async def test_http_status_retry_matrix(
        self, client: MCPClient, status: int, should_reinit: bool, should_retry: bool
    ) -> None:
        old_session = AsyncMock()
        new_session = AsyncMock()
        client.sessions = {"test-server": old_session}
        client._create_session = AsyncMock(return_value=new_session)

        req = httpx.Request("POST", "http://example.com/mcp")
        resp = httpx.Response(status, request=req)
        err = httpx.HTTPStatusError(f"status {status}", request=req, response=resp)

        calls: list[str] = []

        async def attempt(sess):
            calls.append("call")
            # First attempt fails with status error
            if len(calls) == 1:
                raise err
            return "ok"

        if should_retry:
            assert await client._run_with_recovery("test-server", "op", attempt) == "ok"
            assert len(calls) == 2
        else:
            with pytest.raises(httpx.HTTPStatusError):
                await client._run_with_recovery("test-server", "op", attempt)
            assert len(calls) == 1

        if should_reinit:
            client._create_session.assert_called_once()
        else:
            client._create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_jsonrpc_error_does_not_retry(self, client: MCPClient):
        old_session = AsyncMock()
        client.sessions = {"test-server": old_session}

        client._create_session = AsyncMock()
        mcp_err = McpError(ErrorData(code=-32602, message="Invalid params"))

        async def attempt(_sess):
            raise mcp_err

        with pytest.raises(McpError):
            await client._run_with_recovery("test-server", "op", attempt)

        client._create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_429_retries_without_reinit(self, client: MCPClient) -> None:
        old_session = AsyncMock()
        client.sessions = {"test-server": old_session}
        client._create_session = AsyncMock()

        req = httpx.Request("POST", "http://example.com/mcp")
        resp = httpx.Response(429, request=req)
        err = httpx.HTTPStatusError("rate limited", request=req, response=resp)

        calls = 0

        async def attempt(_sess):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise err
            return "ok"

        # Avoid sleeping in unit tests
        with patch("tarsy.integrations.mcp.client.asyncio.sleep", new=AsyncMock()) as _sleep:
            assert await client._run_with_recovery("test-server", "op", attempt) == "ok"
            assert calls == 2
            client._create_session.assert_not_called()
            _sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transport_error_retries_with_reinit(self, client: MCPClient) -> None:
        old_session = AsyncMock()
        new_session = AsyncMock()
        client.sessions = {"test-server": old_session}
        client._create_session = AsyncMock(return_value=new_session)

        req = httpx.Request("POST", "http://example.com/mcp")
        err = httpx.ConnectError("connect failed", request=req)

        calls = 0

        async def attempt(_sess):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise err
            return "ok"

        assert await client._run_with_recovery("test-server", "op", attempt) == "ok"
        assert calls == 2
        client._create_session.assert_called_once()
