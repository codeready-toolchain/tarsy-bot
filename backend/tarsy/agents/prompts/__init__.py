"""
LangChain-based prompt building package.

This package provides a clean template composition system for building
prompts using LangChain templates while maintaining backward compatibility
with the existing PromptBuilder API.
"""

from .builders import PromptBuilder
from .components import PromptContext

# Create shared instance
_shared_prompt_builder = PromptBuilder()


def get_prompt_builder() -> PromptBuilder:
    """Get the shared PromptBuilder instance."""
    return _shared_prompt_builder


# Re-export for backward compatibility
__all__ = ['PromptBuilder', 'PromptContext', 'get_prompt_builder']
