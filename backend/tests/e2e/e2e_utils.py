"""
Shared utilities for E2E tests.

This module contains common functionality used across multiple E2E test files
to reduce duplication and improve maintainability.
"""

import asyncio
import re
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock, patch

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
    
    # Ensure we have enough expected messages to compare
    assert (
        len(expected_messages) >= n
    ), f"Expected messages count insufficient: need at least {n} messages, got {len(expected_messages)}"
    
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
        
        if expected_content != actual_content:
            # Show difference for debugging
            print(f"\n❌ Content mismatch in message {i}:")
            print(f"  Expected role: {expected_role}")
            print(f"  Actual role: {actual_role}")
            print(f"  Expected length: {len(expected_content)}")
            print(f"  Actual length: {len(actual_content)}")
            print(f"  Expected preview: {expected_content[:200]}...")
            print(f"  Actual preview: {actual_content[:200]}...")
            
            # Find where they differ
            for idx, (e_char, a_char) in enumerate(zip(expected_content, actual_content)):
                if e_char != a_char:
                    print(f"  First difference at position {idx}:")
                    print(f"    Expected: ...{expected_content[max(0,idx-50):idx+50]}...")
                    print(f"    Actual:   ...{actual_content[max(0,idx-50):idx+50]}...")
                    break
            else:
                # One is longer than the other
                min_len = min(len(expected_content), len(actual_content))
                print(f"  Strings match until position {min_len}, then one continues:")
                if len(expected_content) > len(actual_content):
                    print(f"    Expected has extra: {expected_content[min_len:]}")
                else:
                    print(f"    Actual has extra: {actual_content[min_len:]}")
        
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
        
        # Strip leading/trailing whitespace for consistent comparison
        content = content.strip()
        
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

        async def mock_call_tool(self, server_name: str, tool_name: str, parameters, session_id: str, stage_execution_id=None, investigation_conversation=None, mcp_selection=None, configured_servers=None, parent_stage_execution_id=None, parallel_index=None, agent_name=None):
            """Override call_tool to use our mock sessions."""
            # Ensure our mock sessions are available
            self.sessions = mock_sessions.copy()
            self._initialized = True
            # Call the original method which will now use our mock sessions
            return await original_call_tool(self, server_name, tool_name, parameters, session_id, stage_execution_id, investigation_conversation, mcp_selection, configured_servers, parent_stage_execution_id, parallel_index, agent_name)

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
    async def wait_for_parallel_execution_statuses(
        e2e_test_client,
        session_id: str,
        stage_name: str,
        expected_statuses: dict[str, str],
        max_wait_seconds: float = 10.0,
        poll_interval: float = 0.1
    ) -> dict[str, Any]:
        """
        Wait for parallel execution statuses to match expected values.
        
        This helps avoid race conditions where session status updates before
        child parallel execution statuses are committed to the database.
        
        Args:
            e2e_test_client: Test client for making API calls
            session_id: The session ID to check
            stage_name: Name of the parallel stage to check
            expected_statuses: Dict mapping agent names to expected statuses (e.g., {"LogAgent": "completed"})
            max_wait_seconds: Maximum time to wait for statuses to match
            poll_interval: Time between polling attempts
            
        Returns:
            stage_data: The stage data once statuses match
            
        Raises:
            AssertionError: If statuses don't match within timeout
        """
        import asyncio
        start_time = asyncio.get_event_loop().time()
        attempt = 0
        
        while True:
            attempt += 1
            elapsed = asyncio.get_event_loop().time() - start_time
            
            # Get current session details
            detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
            stages = detail_data.get("stages", [])
            
            # Find the target stage
            target_stage = next((s for s in stages if s["stage_name"] == stage_name), None)
            if target_stage is None:
                if elapsed >= max_wait_seconds:
                    raise AssertionError(f"Stage '{stage_name}' not found after {max_wait_seconds}s")
                await asyncio.sleep(poll_interval)
                continue
            
            # Check parallel executions
            parallel_executions = target_stage.get("parallel_executions", [])
            if not parallel_executions:
                if elapsed >= max_wait_seconds:
                    raise AssertionError(f"No parallel executions found for stage '{stage_name}' after {max_wait_seconds}s")
                await asyncio.sleep(poll_interval)
                continue
            
            # First check if all expected agents are present
            all_agents_present = True
            current_statuses = {}
            for agent_name, expected_status in expected_statuses.items():
                agent_exec = next((e for e in parallel_executions if e.get("agent") == agent_name), None)
                if agent_exec is None:
                    all_agents_present = False
                    current_statuses[agent_name] = "NOT_FOUND"
                else:
                    current_statuses[agent_name] = agent_exec.get("status")
            
            # If not all agents present yet, wait and retry (unless timeout)
            if not all_agents_present:
                if elapsed >= max_wait_seconds:
                    raise AssertionError(
                        f"Not all expected agents found after {max_wait_seconds}s:\n"
                        f"Expected agents: {list(expected_statuses.keys())}\n"
                        f"Current statuses: {current_statuses}"
                    )
                await asyncio.sleep(poll_interval)
                continue
            
            # Check if all statuses match
            all_match = True
            for agent_name, expected_status in expected_statuses.items():
                actual_status = current_statuses[agent_name]
                if actual_status != expected_status:
                    all_match = False
                    break
            
            if all_match:
                print(f"✅ Parallel execution statuses verified after {elapsed:.2f}s (attempt {attempt})")
                return target_stage
            
            # Log mismatches every 10 attempts to help diagnose issues
            if attempt % 10 == 0:
                print(f"🔄 Still waiting for status match (attempt {attempt}, {elapsed:.2f}s): Expected {expected_statuses}, Got {current_statuses}")
            
            # Check timeout
            if elapsed >= max_wait_seconds:
                # Get fresh data for better error message
                final_detail = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                final_stages = final_detail.get("stages", [])
                final_stage = next((s for s in final_stages if s["stage_name"] == stage_name), None)
                
                error_msg = (
                    f"Parallel execution statuses did not match after {max_wait_seconds}s:\n"
                    f"Expected: {expected_statuses}\n"
                    f"Got: {current_statuses}\n"
                    f"Session status: {final_detail.get('status')}\n"
                    f"Stage status: {final_stage.get('status') if final_stage else 'NOT_FOUND'}"
                )
                
                # Include LLM interaction counts for debugging
                if final_stage and final_stage.get("parallel_executions"):
                    error_msg += "\nParallel execution details:"
                    for exec in final_stage["parallel_executions"]:
                        llm_count = len(exec.get("llm_interactions", []))
                        error_msg += f"\n  - {exec.get('agent')}: status={exec.get('status')}, llm_interactions={llm_count}"
                
                raise AssertionError(error_msg)
            
            # Wait before next poll
            await asyncio.sleep(poll_interval)

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

    @staticmethod
    def create_agent_aware_streaming_mock(agent_counters: dict, agent_responses: dict, agent_identifiers: dict):
        """
        Create an agent-aware streaming mock for LangChain LLM clients.
        
        This factory creates a mock that identifies which agent is calling based on system message content
        and returns appropriate responses from the agent_responses dictionary.
        
        Args:
            agent_counters: Dict tracking interaction count per agent (will be mutated)
            agent_responses: Dict mapping agent names to lists of response data
            agent_identifiers: Dict mapping agent names to identifier strings in system messages
                              e.g., {"LogAgent": "log analysis specialist"}
        
        Returns:
            Mock astream function that can be used to patch LangChain clients
            
        Example:
            agent_counters = {"LogAgent": 0, "SynthesisAgent": 0}
            agent_responses = {
                "LogAgent": [
                    {"response_content": "...", "input_tokens": 200, "output_tokens": 75, "total_tokens": 275}
                ]
            }
            agent_identifiers = {"LogAgent": "log analysis specialist"}
            
            streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
                agent_counters, agent_responses, agent_identifiers
            )
        """
        from .conftest import create_mock_stream
        
        def create_streaming_mock():
            """Create a mock astream function that identifies the agent and returns appropriate responses."""
            async def mock_astream(*args, **kwargs):
                # Identify which agent is calling by inspecting the conversation
                agent_name = "Unknown"
                
                # Extract messages from args
                # When patching instance methods, args[0] is 'self', args[1] is the messages
                messages = []
                if args and len(args) > 1:
                    messages = args[1] if isinstance(args[1], list) else []
                elif args and len(args) > 0 and isinstance(args[0], list):
                    # Fallback: if args[0] is a list, use it (shouldn't happen with patch.object)
                    messages = args[0]
                
                # Look for agent-specific instructions in the system message
                for msg in messages:
                    # Handle both dict and Message object formats
                    content = ""
                    msg_type = ""
                    
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        msg_type = msg.get("role", "") or msg.get("type", "")
                    elif hasattr(msg, "content"):
                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                        msg_type = getattr(msg, "type", "") or msg.__class__.__name__.lower().replace("message", "")
                    
                    # Check if this is a system message  
                    if msg_type in ["system", "systemmessage"]:
                        # Check all agent identifiers
                        for agent, identifier in agent_identifiers.items():
                            if identifier.lower() in content.lower():
                                agent_name = agent
                                break
                        if agent_name != "Unknown":
                            break
                
                # Get the next response for this agent
                if agent_name in agent_counters:
                    agent_interaction_num = agent_counters[agent_name]
                    agent_counters[agent_name] += 1
                
                    print(f"\n🔍 LLM REQUEST from {agent_name} (interaction #{agent_interaction_num + 1})")
                
                    # Get response for this agent's interaction
                    agent_response_list = agent_responses.get(agent_name, [])
                    if agent_interaction_num < len(agent_response_list):
                        response_data = agent_response_list[agent_interaction_num]
                    else:
                        response_data = {
                            "response_content": f"Default response for {agent_name}",
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 150
                        }
                else:
                    response_data = {
                        "response_content": "Default response",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150
                    }
                
                content = response_data["response_content"]
                usage_metadata = {
                    "input_tokens": response_data["input_tokens"],
                    "output_tokens": response_data["output_tokens"],
                    "total_tokens": response_data["total_tokens"]
                }
                
                # Yield chunks from the mock stream - must be an async generator
                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk
            
            return mock_astream
        
        return create_streaming_mock()

    @staticmethod
    async def run_with_timeout(coro, timeout_seconds: float = 120.0, test_name: str = "Test"):
        """
        Run a coroutine with timeout and proper cleanup.
        
        This utility wraps async test execution with a timeout mechanism,
        ensuring proper task cancellation if the timeout is exceeded.
        
        Args:
            coro: Coroutine to execute
            timeout_seconds: Maximum time to wait in seconds (default: 120.0)
            test_name: Name of the test for error messages (default: "Test")
            
        Returns:
            The result of the coroutine execution
            
        Raises:
            AssertionError: If the coroutine exceeds the timeout
            Exception: Any exception raised by the coroutine
            
        Example:
            async def run_test():
                # Test logic here
                return result
            
            result = await E2ETestUtils.run_with_timeout(
                run_test(),
                timeout_seconds=120.0,
                test_name="LangChain failure test"
            )
        """
        try:
            task = asyncio.create_task(coro)
            _, pending = await asyncio.wait({task}, timeout=timeout_seconds)
            
            if pending:
                for t in pending:
                    t.cancel()
                print(f"❌ TIMEOUT: {test_name} exceeded {timeout_seconds} seconds!")
                raise AssertionError(f"{test_name} exceeded timeout of {timeout_seconds} seconds")
            else:
                return task.result()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            raise

    @staticmethod
    @contextmanager
    def create_llm_patch_context(gemini_mock_factory=None, streaming_mock=None):
        """
        Create a context manager that patches LLM clients.
        
        This is a static version of the method from ParallelTestBase, making it
        available to all E2E tests without needing to inherit from a base class.
        
        Args:
            gemini_mock_factory: Optional factory for Gemini SDK mocking (native thinking)
            streaming_mock: Optional mock for LangChain streaming (ReAct)
            
        Yields:
            None (patches are active within the context)
            
        Example:
            with E2ETestUtils.create_llm_patch_context(gemini_mock, streaming_mock):
                # Test code here with patched LLM clients
        """
        from langchain_anthropic import ChatAnthropic
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
        from langchain_xai import ChatXAI
        
        patches = []
        
        # Patch Gemini SDK if provided
        if gemini_mock_factory:
            patches.append(
                patch("tarsy.integrations.llm.gemini_client.genai.Client", gemini_mock_factory)
            )
        
        # Patch LangChain clients if streaming mock provided
        if streaming_mock:
            patches.extend([
                patch.object(BaseChatModel, 'astream', streaming_mock),
                patch.object(ChatOpenAI, 'astream', streaming_mock),
                patch.object(ChatAnthropic, 'astream', streaming_mock),
                patch.object(ChatXAI, 'astream', streaming_mock),
                patch.object(ChatGoogleGenerativeAI, 'astream', streaming_mock)
            ])
        
        # Apply all patches
        started_patches = []
        try:
            for p in patches:
                started_patches.append(p.start())
            yield
        finally:
            # Stop all patches
            for p in patches:
                p.stop()
