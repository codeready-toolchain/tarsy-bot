"""
Shared test helpers for LLM client tests.

This module provides shared MockChunk and create_mock_stream helpers
used across multiple test files to avoid duplication.
"""

from typing import Optional


class MockChunk:
    """Mock chunk that supports LangChain-style aggregation with + operator."""

    def __init__(self, content: str, usage_metadata: Optional[dict] = None):
        self.content = content
        self.usage_metadata = usage_metadata

    def __add__(self, other):
        """Support chunk aggregation like LangChain does."""
        if not isinstance(other, MockChunk):
            return NotImplemented
        # Aggregate content and usage_metadata
        new_content = self.content + other.content
        # For usage metadata, the last one wins (simulating LangChain behavior)
        new_usage = other.usage_metadata or self.usage_metadata
        return MockChunk(new_content, new_usage)

    def __radd__(self, other):
        """Support reverse addition."""
        if other is None:
            return self
        return self.__add__(other)


async def create_mock_stream(content: str, usage_metadata: Optional[dict] = None):
    """
    Create an async generator that yields mock chunks.

    Args:
        content: The content to stream, yielded character by character
        usage_metadata: Optional usage metadata to attach to the final chunk
    """
    # Simulate streaming by yielding content in chunks
    for i, char in enumerate(content):
        # Add usage_metadata only to the final chunk (simulates OpenAI stream_usage=True)
        is_final = i == len(content) - 1
        yield MockChunk(char, usage_metadata=usage_metadata if is_final else None)


def create_stream_side_effect(content: str, usage_metadata: Optional[dict] = None):
    """
    Create a side_effect function that returns a mock stream.

    This is used to avoid lambda functions with unused *args/**kwargs.
    The returned side_effect accepts any arguments (to match astream signature)
    but ignores them.

    Args:
        content: The content to stream
        usage_metadata: Optional usage metadata for the final chunk

    Returns:
        A function that accepts any args/kwargs and returns an async generator
    """

    def side_effect(*_args, **_kwargs):
        """Accept and ignore any arguments to match astream signature."""
        return create_mock_stream(content, usage_metadata)

    return side_effect

