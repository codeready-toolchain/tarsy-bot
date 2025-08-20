"""
LangChain-based prompt building package.

This package provides a clean template composition system for building
prompts using LangChain templates.
"""

from .builders import PromptBuilder

# Create shared instance
_shared_prompt_builder = PromptBuilder()


def get_prompt_builder() -> PromptBuilder:
    """Get the shared PromptBuilder instance."""
    return _shared_prompt_builder


# Re-export for backward compatibility
__all__ = ['PromptBuilder', 'get_prompt_builder']
