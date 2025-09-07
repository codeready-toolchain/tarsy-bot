"""
Shared utilities for E2E tests.

This module contains common functionality used across multiple E2E test files
to reduce duplication and improve maintainability.
"""

import asyncio
import time
from typing import Tuple, Dict, Any, List, Callable
from unittest.mock import AsyncMock

import httpx
from mcp.types import Tool


class E2ETestUtils:
    """Shared utility methods for E2E tests."""
    
    @staticmethod
    def get_e2e_jwt_token(settings=None) -> str:
        """
        Generate a real JWT token for E2E tests using the dev keys.
        
        Args:
            settings: Optional settings object to use. If None, will try get_settings()
        
        Returns:
            Valid JWT token string for E2E authentication
        """
        try:
            from tarsy.services.jwt_service import JWTService
            from tarsy.config.settings import get_settings
            
            # Use provided settings or fall back to get_settings() 
            if settings is None:
                settings = get_settings()
            jwt_service = JWTService(settings)
            
            # Create a test user token with correct method signature
            return jwt_service.create_user_jwt_token(
                user_id="e2e_test_user_123",
                username="e2e-test-user", 
                email="e2e-test@example.com",
                avatar_url="https://github.com/e2e-test.png"
            )
            
        except Exception as e:
            # Fallback for cases where JWT service is not available
            print(f"⚠️  Could not generate real JWT token: {e}")
            print("🔧 Using fallback mock token")
            return "mock_e2e_jwt_token"
    
    @staticmethod
    def get_auth_headers(settings=None) -> Dict[str, str]:
        """
        Get authentication headers for E2E API requests.
        
        Args:
            settings: Optional settings object to use for JWT generation
            
        Returns:
            Dictionary with Authorization header containing Bearer token
        """
        token = E2ETestUtils.get_e2e_jwt_token(settings)
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    async def wait_for_session_completion(
        e2e_test_client, max_wait_seconds: int = 8, debug_logging: bool = False
    ) -> Tuple[str, str]:
        """
        Robust polling logic to wait for session completion.

        Args:
            e2e_test_client: Test client for making API calls
            max_wait_seconds: Maximum time to wait in seconds
            debug_logging: Whether to enable detailed debug logging

        Returns:
            Tuple of (session_id, final_status)

        Raises:
            AssertionError: If no session found or polling times out
        """
        print(f"⏱️ Starting robust polling (max {max_wait_seconds}s)...")

        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.2  # Poll every 200ms for responsiveness
        attempts = 0

        while True:
            attempts += 1
            elapsed_time = asyncio.get_event_loop().time() - start_time

            # Check for timeout
            if elapsed_time >= max_wait_seconds:
                print(f"❌ Polling timeout after {elapsed_time:.1f}s ({attempts} attempts)")
                # Print debug info about the current state
                if debug_logging:
                    try:
                        headers = E2ETestUtils.get_auth_headers()
                        sessions_response = e2e_test_client.get("/api/v1/history/sessions", headers=headers)
                        if sessions_response.status_code == 200:
                            sessions_data = sessions_response.json()
                            sessions = sessions_data.get("sessions", [])
                            print(f"🔍 Debug: Found {len(sessions)} sessions")
                            if sessions:
                                session = sessions[0]
                                print(f"🔍 Debug: Latest session: {session.get('session_id')} -> {session.get('status')}")
                        else:
                            print(f"🔍 Debug: Failed to get sessions: {sessions_response.status_code}")
                    except Exception as e:
                        print(f"🔍 Debug: Exception during debug polling: {e}")
                raise AssertionError(f"Polling timeout after {elapsed_time:.1f}s")

            try:
                # Get current sessions
                headers = E2ETestUtils.get_auth_headers()
                sessions_response = e2e_test_client.get("/api/v1/history/sessions", headers=headers)
                if sessions_response.status_code != 200:
                    print(f"⚠️ Failed to get sessions: {sessions_response.status_code}")
                    await asyncio.sleep(poll_interval)
                    continue

                sessions_data = sessions_response.json()
                sessions = sessions_data.get("sessions", [])

                if sessions:
                    session = sessions[0]  # Get the most recent session
                    session_id = session.get("session_id")
                    status = session.get("status")

                    if debug_logging:
                        print(f"🔍 Polling attempt {attempts} (elapsed: {elapsed_time:.1f}s): Session {session_id} -> {status}")

                    # Check if session is complete (either successful or failed)
                    if status in ["completed", "failed"]:
                        print(f"✅ Session completed with status: {status}")
                        return session_id, status

                    # If session is still processing, continue polling
                    if status in ["processing", "queued"]:
                        await asyncio.sleep(poll_interval)
                        continue

                    # Unknown status, continue polling
                    print(f"⚠️ Unknown session status: {status}, continuing to poll...")
                    await asyncio.sleep(poll_interval)
                    continue

                else:
                    # No sessions yet, continue polling
                    await asyncio.sleep(poll_interval)
                    continue

            except Exception as e:
                print(f"⚠️ Exception during polling: {e}")
                await asyncio.sleep(poll_interval)
                continue

    @staticmethod
    def create_test_mcp_servers(base_servers: Dict[str, Any], server_configs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create test MCP server configurations by extending base servers.

        Args:
            base_servers: Base MCP server configurations (e.g., BUILTIN_MCP_SERVERS)
            server_configs: Dictionary of server configurations to add/override

        Returns:
            Dictionary of MCP server configurations for testing
        """
        test_servers = base_servers.copy()
        for server_name, config in server_configs.items():
            test_servers[server_name] = config
        return test_servers

    @staticmethod
    def setup_runbook_mocking(respx_mock, content: str = "# Mock Runbook\nTest runbook content") -> None:
        """
        Setup HTTP mocking for runbook sources.

        Args:
            respx_mock: The respx mock object
            content: Content to return for runbook requests
        """
        respx_mock.get(url__regex=r".*(github\.com|runbooks\.example\.com).*").mock(
            return_value=httpx.Response(200, text=content)
        )

    @staticmethod
    def create_mcp_client_patches(mock_sessions: Dict[str, AsyncMock]) -> Tuple[Callable, Callable]:
        """
        Create MCP client patches for testing.

        Args:
            mock_sessions: Dictionary mapping server names to mock session objects

        Returns:
            Tuple of (mock_list_tools, mock_call_tool) functions
        """
        from tarsy.integrations.mcp.client import MCPClient

        original_list_tools = MCPClient.list_tools
        original_call_tool = MCPClient.call_tool

        async def mock_list_tools(self, session_id: str, server_name=None, stage_execution_id=None):
            """Override list_tools to use our mock sessions."""
            # Ensure our mock sessions are available
            self.sessions = mock_sessions.copy()
            self._initialized = True
            # Call the original method which will now use our mock sessions
            return await original_list_tools(self, session_id, server_name, stage_execution_id)

        async def mock_call_tool(self, server_name: str, tool_name: str, parameters, session_id: str, stage_execution_id=None, investigation_conversation=None):
            """Override call_tool to use our mock sessions."""
            # Ensure our mock sessions are available
            self.sessions = mock_sessions.copy()
            self._initialized = True
            # Call the original method which will now use our mock sessions
            return await original_call_tool(self, server_name, tool_name, parameters, session_id, stage_execution_id, investigation_conversation)

        return mock_list_tools, mock_call_tool

    @staticmethod
    def create_simple_kubernetes_mcp_config(command_args: List[str] = ["test"], instructions: str = "Test server") -> Dict[str, Any]:
        """
        Create a simple kubernetes MCP server configuration for testing.

        Args:
            command_args: Command arguments for the MCP server
            instructions: Instructions for the MCP server

        Returns:
            MCP server configuration dictionary
        """
        return {
            "server_id": "kubernetes-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {"command": "echo", "args": command_args},
            "instructions": instructions,
            "data_masking": {"enabled": False}
        }

    @staticmethod
    def create_simple_data_server_mcp_config(command_args: List[str] = ["test"], instructions: str = "Test data server") -> Dict[str, Any]:
        """
        Create a simple data server MCP server configuration for testing.

        Args:
            command_args: Command arguments for the MCP server
            instructions: Instructions for the MCP server

        Returns:
            MCP server configuration dictionary
        """
        return {
            "server_id": "test-data-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {"command": "echo", "args": command_args},
            "instructions": instructions,
            "data_masking": {"enabled": False}
        }

    @staticmethod
    def create_generic_mcp_session_mock(response_text: str = "Mock response") -> AsyncMock:
        """
        Create a generic MCP session mock for simple testing scenarios.

        Args:
            response_text: Text to return for tool calls

        Returns:
            Mock MCP session object
        """
        mock_session = AsyncMock()

        async def mock_call_tool(tool_name, _parameters):
            mock_result = AsyncMock()
            mock_content = AsyncMock()
            mock_content.text = f"Mock {tool_name} response"
            mock_result.content = [mock_content]
            return mock_result

        async def mock_list_tools():
            mock_tool = Tool(
                name="generic_tool",
                description="Generic test tool",
                inputSchema={"type": "object", "properties": {}}
            )

            mock_result = AsyncMock()
            mock_result.tools = [mock_tool]
            return mock_result

        mock_session.call_tool.side_effect = mock_call_tool
        mock_session.list_tools.side_effect = mock_list_tools

        return mock_session

    @staticmethod
    def submit_alert(e2e_test_client, alert_data: Dict[str, Any]) -> str:
        """
        Submit an alert and return the alert ID.

        Args:
            e2e_test_client: Test client for making API calls
            alert_data: Alert data to submit

        Returns:
            alert_id: The ID of the submitted alert

        Raises:
            AssertionError: If submission fails or response is invalid
        """
        print("🚀 Submitting alert")
        headers = E2ETestUtils.get_auth_headers()
        response = e2e_test_client.post("/alerts", json=alert_data, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Alert submission failed with status {response.status_code}")
            print(f"Response: {response.text}")
        assert response.status_code == 200

        response_data = response.json()
        assert response_data["status"] == "queued"
        alert_id = response_data["alert_id"]
        print(f"✅ Alert submitted: {alert_id}")

        return alert_id

    @staticmethod
    def submit_alert_with_settings(e2e_test_client, alert_data: Dict[str, Any], settings) -> str:
        """
        Submit an alert using provided E2E settings and return the alert ID.

        Args:
            e2e_test_client: Test client for making API calls
            alert_data: Alert data to submit
            settings: E2E settings object with correct JWT configuration

        Returns:
            alert_id: The ID of the submitted alert

        Raises:
            AssertionError: If submission fails or response is invalid
        """
        print("🚀 Submitting alert with E2E settings")
        headers = E2ETestUtils.get_auth_headers(settings)
        response = e2e_test_client.post("/alerts", json=alert_data, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Alert submission failed with status {response.status_code}")
            print(f"Response: {response.text}")
        assert response.status_code == 200

        response_data = response.json()
        assert response_data["status"] == "queued"
        alert_id = response_data["alert_id"]
        print(f"✅ Alert submitted: {alert_id}")

        return alert_id

    @staticmethod
    def get_session_details(e2e_test_client, session_id: str, max_retries: int = 1, retry_delay: float = 0.5) -> Dict[str, Any]:
        """
        Get session details with optional retry logic for robustness.

        Args:
            e2e_test_client: Test client for making API calls
            session_id: The session ID to get details for
            max_retries: Maximum number of retries (default 1 = no retry)
            retry_delay: Delay between retries in seconds

        Returns:
            detail_data: Session detail data

        Raises:
            AssertionError: If session details cannot be retrieved
        """
        for attempt in range(max_retries):
            headers = E2ETestUtils.get_auth_headers()
            session_detail_response = e2e_test_client.get(f"/api/v1/history/sessions/{session_id}", headers=headers)
            assert session_detail_response.status_code == 200

            detail_data = session_detail_response.json()

            # If this isn't the last attempt and we want to retry, wait and continue
            if attempt < max_retries - 1:
                stages = detail_data.get("stages", [])
                if len(stages) == 0:  # No stages yet, might need to wait
                    print(f"🔄 Waiting for stages to be available (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue

            # Return data on last attempt or if we have stages
            return detail_data

        # This should never be reached due to the loop logic, but just in case
        raise AssertionError(f"Failed to get session details after {max_retries} attempts")
