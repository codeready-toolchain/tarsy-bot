"""
Unit tests for MCP transport error handling utilities.
"""

import httpx
import pytest

from tarsy.integrations.mcp.transport.error_handling import (
    is_cancel_scope_mismatch_error,
    is_safe_teardown_error,
)


@pytest.mark.unit
class TestIsCancelScopeMismatchError:
    """Tests for is_cancel_scope_mismatch_error function."""

    def test_detects_cancel_scope_mismatch_error(self) -> None:
        """Test that it detects the specific AnyIO cancel scope mismatch error."""
        error = RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")
        assert is_cancel_scope_mismatch_error(error) is True

    def test_detects_partial_message_match(self) -> None:
        """Test that it detects the error even with surrounding text."""
        error = RuntimeError(
            "Some context: Attempted to exit cancel scope in a different task than it was entered in - additional info"
        )
        assert is_cancel_scope_mismatch_error(error) is True

    def test_rejects_other_runtime_errors(self) -> None:
        """Test that it doesn't match other RuntimeErrors."""
        error = RuntimeError("Some other runtime error")
        assert is_cancel_scope_mismatch_error(error) is False

    def test_rejects_non_runtime_errors(self) -> None:
        """Test that it doesn't match non-RuntimeError exceptions."""
        error = ValueError("Attempted to exit cancel scope in a different task than it was entered in")
        assert is_cancel_scope_mismatch_error(error) is False

    def test_rejects_none(self) -> None:
        """Test that it safely handles unexpected input."""
        # Should not raise, just return False
        assert is_cancel_scope_mismatch_error(ValueError()) is False


@pytest.mark.unit
class TestIsSafeTeardownError:
    """Tests for is_safe_teardown_error function."""

    def test_cancel_scope_mismatch_is_safe(self) -> None:
        """Test that cancel scope mismatch errors are considered safe."""
        error = RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")
        assert is_safe_teardown_error(error) is True

    def test_httpx_connect_error_is_safe(self) -> None:
        """Test that httpx ConnectError is considered safe."""
        error = httpx.ConnectError("Connection failed")
        assert is_safe_teardown_error(error) is True

    def test_httpx_transport_error_is_safe(self) -> None:
        """Test that httpx TransportError is considered safe."""
        error = httpx.TransportError("Transport failed")
        assert is_safe_teardown_error(error) is True

    def test_generator_exit_is_safe(self) -> None:
        """Test that GeneratorExit is considered safe."""
        error = GeneratorExit()
        assert is_safe_teardown_error(error) is True

    def test_base_exception_group_with_all_safe_errors(self) -> None:
        """Test that BaseExceptionGroup with all safe errors is safe."""
        error = BaseExceptionGroup(
            "multiple errors",
            [
                httpx.ConnectError("conn1"),
                httpx.TransportError("trans1"),
                RuntimeError("Attempted to exit cancel scope in a different task than it was entered in"),
            ],
        )
        assert is_safe_teardown_error(error) is True

    def test_base_exception_group_with_mixed_errors_is_not_safe(self) -> None:
        """Test that BaseExceptionGroup with any unsafe error is not safe."""
        error = BaseExceptionGroup(
            "multiple errors",
            [
                httpx.ConnectError("conn1"),
                ValueError("This is not safe"),  # Not a safe error
            ],
        )
        assert is_safe_teardown_error(error) is False

    def test_nested_exception_groups_all_safe(self) -> None:
        """Test nested BaseExceptionGroups where all are safe."""
        inner_group = BaseExceptionGroup(
            "inner",
            [
                httpx.ConnectError("conn1"),
                GeneratorExit(),
            ],
        )
        outer_group = BaseExceptionGroup(
            "outer",
            [
                inner_group,
                httpx.TransportError("trans1"),
            ],
        )
        assert is_safe_teardown_error(outer_group) is True

    def test_nested_exception_groups_with_unsafe_error(self) -> None:
        """Test nested BaseExceptionGroups with an unsafe error deep inside."""
        inner_group = BaseExceptionGroup(
            "inner",
            [
                httpx.ConnectError("conn1"),
                RuntimeError("Some other error"),  # Not safe
            ],
        )
        outer_group = BaseExceptionGroup(
            "outer",
            [
                inner_group,
                httpx.TransportError("trans1"),
            ],
        )
        assert is_safe_teardown_error(outer_group) is False

    def test_regular_exceptions_are_not_safe(self) -> None:
        """Test that regular exceptions are not considered safe."""
        assert is_safe_teardown_error(ValueError("error")) is False
        assert is_safe_teardown_error(RuntimeError("other error")) is False
        assert is_safe_teardown_error(Exception("generic")) is False
        assert is_safe_teardown_error(KeyError("key")) is False

    def test_http_status_errors_are_not_safe(self) -> None:
        """Test that httpx HTTPStatusError is not considered safe."""
        # Create a mock response
        request = httpx.Request("GET", "http://test.com")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("Server error", request=request, response=response)
        assert is_safe_teardown_error(error) is False

    def test_empty_exception_group_is_safe(self) -> None:
        """Test that an empty BaseExceptionGroup is considered safe."""
        # Edge case: group with no exceptions
        try:
            error = BaseExceptionGroup("empty", [])
        except ValueError:
            # BaseExceptionGroup requires at least one exception in some Python versions
            pytest.skip("BaseExceptionGroup requires at least one exception")
        else:
            # If we can create an empty group, it should be safe (vacuous truth)
            assert is_safe_teardown_error(error) is True

    def test_single_exception_in_group(self) -> None:
        """Test BaseExceptionGroup with single safe exception."""
        error = BaseExceptionGroup(
            "single",
            [httpx.ConnectError("conn")],
        )
        assert is_safe_teardown_error(error) is True

    def test_single_unsafe_exception_in_group(self) -> None:
        """Test BaseExceptionGroup with single unsafe exception."""
        error = BaseExceptionGroup(
            "single",
            [ValueError("bad")],
        )
        assert is_safe_teardown_error(error) is False

