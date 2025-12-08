"""
Shared utilities for E2E tests.

This module contains common functionality used across multiple E2E test files
to reduce duplication and improve maintainability.
"""

import asyncio
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock

from mcp.types import Tool


def assert_conversation_messages(
    expected_conversation: dict, actual_messages: list, n: int
):
    """
    Get the first N messages from expected_conversation['messages'] and compare with actual_messages.

    Args:
        expected_conversation: Dictionary with 'messages' key containing expected message list
        actual_messages: List of actual messages from the LLM interaction
        n: Number of messages to compare (a count)
    """
    expected_messages = expected_conversation.get("messages", [])
    assert (
        len(actual_messages) == n
    ), f"Actual messages count mismatch: expected {n}, got {len(actual_messages)}"

    # Extract first N messages
    first_n_expected = expected_messages[:n]

    # Compare each message
    for i in range(len(first_n_expected)):
        assert (
            i < len(actual_messages)
        ), f"Missing actual message: Expected {len(first_n_expected)} messages, got {len(actual_messages)}"

        expected_msg = first_n_expected[i]
        actual_msg = actual_messages[i]

        # Compare role
        expected_role = expected_msg.get("role", "")
        actual_role = actual_msg.get("role", "")
        assert (
            expected_role == actual_role
        ), f"Role mismatch: expected {expected_role}, got {actual_role}"

        # Normalize content for comparison
        expected_content = E2ETestUtils.normalize_content(expected_msg.get("content", ""))
        actual_content = E2ETestUtils.normalize_content(actual_msg.get("content", ""))
        
        assert (
            expected_content == actual_content
        ), f"Content mismatch in message {i}: expected length {len(expected_content)}, got {len(actual_content)}"


class E2ETestUtils:
    """Shared utility methods for E2E tests."""

    @staticmethod
    def normalize_content(content: str) -> str:
        """
        Normalize dynamic content in messages for stable comparison.
        
        This function replaces dynamic values (timestamps, UUIDs) with 
        placeholders to enable consistent content comparison across test runs.
        
        Args:
            content: The message content to normalize
            
        Returns:
            Normalized content with placeholders for dynamic values
        """
        # Normalize timestamps (handles microsecond, millisecond, and second precision)
        # Matches timestamps with 10-16 digits (covers all common timestamp formats)
        content = re.sub(r"\*\*Timestamp:\*\*\s*\d{10,16}", "**Timestamp:** {TIMESTAMP}", content)
        content = re.sub(r"Timestamp:\*\*\s*\d{10,16}", "Timestamp:** {TIMESTAMP}", content)
        
        # Normalize alert IDs and session IDs (UUIDs)
        content = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{UUID}",
            content,
        )
        
        # Normalize specific test-generated data keys
        content = re.sub(
            r"test-kubernetes_[a-f0-9]+_\d+", "test-kubernetes_{DATA_KEY}", content
        )
        
        return content

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
                        sessions_response = e2e_test_client.get("/api/v1/history/sessions")
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
                sessions_response = e2e_test_client.get("/api/v1/history/sessions")
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

                    # Check if session is complete (either successful, failed, or paused)
                    if status in ["completed", "failed", "paused"]:
                        print(f"✅ Session completed with status: {status}")
                        return session_id, status

                    # If session is still processing, continue polling
                    # Valid active statuses: pending, in_progress, canceling
                    if status in ["pending", "in_progress", "canceling"]:
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
    def setup_runbook_service_patching(content: str = "# Mock Runbook\nTest runbook content"):
        """
        Setup direct patching of RunbookService.download_runbook method.
        
        This provides consistent behavior regardless of GitHub token configuration:
        - With GitHub token: Bypasses HTTP request and returns mock content
        - Without GitHub token: Bypasses default runbook and returns mock content
        
        Returns a patch context manager that should be used in a 'with' statement.
        
        Args:
            content: Content to return for runbook requests
            
        Returns:
            patch context manager
            
        Example:
            with E2ETestUtils.setup_runbook_service_patching():
                # Test code here
        """
        from unittest.mock import patch
        
        async def mock_download_runbook(self, url: str) -> str:
            """Mock download_runbook that returns consistent content."""
            return content
        
        return patch(
            'tarsy.services.runbook_service.RunbookService.download_runbook',
            mock_download_runbook
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

        async def mock_call_tool(self, server_name: str, tool_name: str, parameters, session_id: str, stage_execution_id=None, investigation_conversation=None, mcp_selection=None, configured_servers=None):
            """Override call_tool to use our mock sessions."""
            # Ensure our mock sessions are available
            self.sessions = mock_sessions.copy()
            self._initialized = True
            # Call the original method which will now use our mock sessions
            return await original_call_tool(self, server_name, tool_name, parameters, session_id, stage_execution_id, investigation_conversation, mcp_selection, configured_servers)

        return mock_list_tools, mock_call_tool

    @staticmethod
    def create_simple_kubernetes_mcp_config(command_args: Optional[List[str]] = None, instructions: str = "Test server") -> Dict[str, Any]:
        """
        Create a simple kubernetes MCP server configuration for testing.

        Args:
            command_args: Command arguments for the MCP server
            instructions: Instructions for the MCP server

        Returns:
            MCP server configuration dictionary
        """
        if command_args is None:
            command_args = ["test"]
        return {
            "server_id": "kubernetes-server",
            "server_type": "test",
            "enabled": True,
            "transport": {
                "type": "stdio",
                "command": "echo",
                "args": command_args
            },
            "instructions": instructions,
            "data_masking": {"enabled": False}
        }

    @staticmethod
    def create_simple_data_server_mcp_config(command_args: Optional[List[str]] = None, instructions: str = "Test data server") -> Dict[str, Any]:
        """
        Create a simple data server MCP server configuration for testing.

        Args:
            command_args: Command arguments for the MCP server
            instructions: Instructions for the MCP server

        Returns:
            MCP server configuration dictionary
        """
        if command_args is None:
            command_args = ["test"]
        return {
            "server_id": "test-data-server",
            "server_type": "test",
            "enabled": True,
            "transport": {
                "type": "stdio",
                "command": "echo",
                "args": command_args
            },
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
            mock_result = Mock()
            mock_content = Mock()
            # Use the provided response_text parameter
            mock_content.text = response_text or f"Mock {tool_name} response"
            mock_result.content = [mock_content]
            return mock_result

        async def mock_list_tools():
            mock_tool = Tool(
                name="generic_tool",
                description="Generic test tool",
                inputSchema={"type": "object", "properties": {}}
            )

            mock_result = Mock()
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
            session_id: The session ID of the submitted alert

        Raises:
            AssertionError: If submission fails or response is invalid
        """
        print("🚀 Submitting alert")
        response = e2e_test_client.post("/api/v1/alerts", json=alert_data)
        assert response.status_code == 200

        response_data = response.json()
        assert response_data["status"] == "queued"
        session_id = response_data["session_id"]
        print(f"✅ Alert submitted: {session_id}")

        return session_id

    @staticmethod
    async def get_session_details_async(e2e_test_client, session_id: str, max_retries: int = 1, retry_delay: float = 0.5) -> Dict[str, Any]:
        """
        Get session details with optional retry logic for robustness (async version).

        This async variant should be used when calling from async contexts to avoid
        blocking the event loop during retries.

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
            session_detail_response = e2e_test_client.get(f"/api/v1/history/sessions/{session_id}")
            assert session_detail_response.status_code == 200

            detail_data = session_detail_response.json()

            # If this isn't the last attempt and we want to retry, wait and continue
            if attempt < max_retries - 1:
                stages = detail_data.get("stages", [])
                if len(stages) == 0:  # No stages yet, might need to wait
                    print(f"🔄 Waiting for stages to be available (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(retry_delay)
                    continue

            # Return data on last attempt or if we have stages
            return detail_data

        # This should never be reached due to the loop logic, but just in case
        raise AssertionError(f"Failed to get session details after {max_retries} attempts")

    @staticmethod
    def get_session_details(e2e_test_client, session_id: str, max_retries: int = 1, retry_delay: float = 0.5) -> Dict[str, Any]:
        """
        Get session details with optional retry logic for robustness (sync version).

        Note: This synchronous version uses time.sleep and will block the event loop
        if called from async contexts. Use get_session_details_async() instead when
        calling from async test functions.

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
            session_detail_response = e2e_test_client.get(f"/api/v1/history/sessions/{session_id}")
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
