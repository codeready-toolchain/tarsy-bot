"""
Backward compatibility re-exports for prompt_builder.

This module provides backward compatibility by re-exporting the new
LangChain-based PromptBuilder and related classes from the prompts package.
"""

# Backward compatibility re-exports
from .prompts import get_prompt_builder, PromptBuilder

__all__ = ['get_prompt_builder', 'PromptBuilder']
