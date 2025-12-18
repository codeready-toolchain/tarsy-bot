"""
Integrations package.

Keep imports lightweight: some integrations have optional third-party dependencies.
We expose a stable API while deferring heavy imports until the symbol is accessed.
"""

from typing import Any

from .mcp import MCPClient

__all__ = ["LLMManager", "LLMClient", "MCPClient"]


def __getattr__(name: str) -> Any:
    if name in ("LLMClient", "LLMManager"):
        # Lazy import to avoid import-time failures when optional dependencies
        # (e.g. google.genai) aren't installed in the current environment.
        from .llm import LLMClient, LLMManager  # noqa: PLC0415

        return LLMClient if name == "LLMClient" else LLMManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")