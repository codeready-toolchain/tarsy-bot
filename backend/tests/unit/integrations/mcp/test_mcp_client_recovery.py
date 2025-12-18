"""
Unit tests for MCP client recovery behavior.

Focuses on retry-once logic for transient HTTP/transport failures and
non-retry behavior for JSON-RPC semantic errors.
"""

from unittest.mock import AsyncMock, Mock

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
    async def test_http_404_triggers_reinit_and_retries_once(self, client: MCPClient):
        old_session = AsyncMock()
        new_session = AsyncMock()
        client.sessions = {"test-server": old_session}

        client._create_session = AsyncMock(return_value=new_session)

        req = httpx.Request("POST", "http://example.com/mcp")
        resp = httpx.Response(404, request=req)
        err = httpx.HTTPStatusError("session not found", request=req, response=resp)

        async def attempt(sess):
            if sess is old_session:
                raise err
            return "ok"

        result = await client._run_with_recovery("test-server", "op", attempt)

        assert result == "ok"
        client._create_session.assert_called_once()

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
    async def test_http_401_does_not_retry(self, client: MCPClient):
        old_session = AsyncMock()
        client.sessions = {"test-server": old_session}

        client._create_session = AsyncMock()

        req = httpx.Request("POST", "http://example.com/mcp")
        resp = httpx.Response(401, request=req)
        err = httpx.HTTPStatusError("unauthorized", request=req, response=resp)

        async def attempt(_sess):
            raise err

        with pytest.raises(httpx.HTTPStatusError):
            await client._run_with_recovery("test-server", "op", attempt)

        client._create_session.assert_not_called()


