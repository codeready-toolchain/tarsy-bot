"""
MCP result summarizer for reducing large tool output sizes using LLM-powered summarization.

This module provides agent-provided summarization of large MCP results after data masking
but before database storage, enabling efficient conversation flow while preserving 
investigation-relevant details.
"""

import copy
import json
from typing import Any, Dict, Optional, TYPE_CHECKING

from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.integrations.llm.client import LLMClient
    from tarsy.agents.prompts.builders import PromptBuilder

logger = get_module_logger(__name__)


class MCPResultSummarizer:
    """Agent-provided MCP result summarizer using LLM client with stage context awareness."""
    
    def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
        """Initialize summarizer with LLM client and prompt builder.
        
        Args:
            llm_client: The LLM client to use for summarization
            prompt_builder: Prompt builder for creating summarization prompts
        """
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
    
    async def summarize_result(
        self,
        server_name: str,
        tool_name: str,
        result: Dict[str, Any],
        investigation_conversation: LLMConversation,
        session_id: str,
        stage_execution_id: Optional[str] = None,
        max_summary_tokens: int = 1000,
        mcp_event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Summarize a large MCP tool result using LLM with investigation conversation context.
        
        Uses LangChain's max_tokens parameter to enforce token limits at the provider level,
        ensuring reliable summarization length control beyond prompt suggestions.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool that produced the result
            result: The original tool result dictionary
            investigation_conversation: The ongoing ReAct conversation for context
            session_id: Session ID for tracking
            stage_execution_id: Optional stage execution ID
            max_summary_tokens: Maximum tokens enforced at LLM provider level via max_tokens
            mcp_event_id: Optional MCP event ID for linking streaming summarization to tool call
            
        Returns:
            Summarized result dictionary with same structure as original
            
        Raises:
            Exception: If summarization fails
        """
        try:
            # Extract the actual result content
            result_content = result.get("result", str(result))
            if isinstance(result_content, dict):
                result_text = json.dumps(result_content, indent=2, default=str)
            else:
                result_text = str(result_content)
            
            # Apply tool result truncation based on current LLM provider limits
            result_text = self._truncate_tool_result_if_needed(result_text)
            
            # Use prompt builder to create summarization prompts
            system_prompt = self.prompt_builder.build_mcp_summarization_system_prompt(
                server_name, tool_name, max_summary_tokens
            )
            system_message = LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)
            
            # Serialize conversation context and build user prompt
            conversation_context = self._serialize_conversation_context(investigation_conversation)
            user_prompt = self.prompt_builder.build_mcp_summarization_user_prompt(
                conversation_context, server_name, tool_name, result_text
            )
            user_message = LLMMessage(role=MessageRole.USER, content=user_prompt)
            
            # Create conversation with both messages (required to start with system message)
            summarization_conversation = LLMConversation(messages=[system_message, user_message])
            
            # Generate summary using LLM client with max_tokens limit (ensures proper hook integration)
            response_conversation = await self.llm_client.generate_response(
                summarization_conversation, session_id, stage_execution_id,
                max_tokens=max_summary_tokens,
                interaction_type=LLMInteractionType.SUMMARIZATION.value,
                mcp_event_id=mcp_event_id
            )
            
            # Extract summary from response
            assistant_message = response_conversation.get_latest_assistant_message()
            if not assistant_message:
                raise Exception("No response from LLM for summarization")
            
            summary_text = assistant_message.content.strip()
            
            # Return summarized result in same structure as original
            # Create a completely new dictionary to avoid unhashable type errors
            summarized_result = {"result": summary_text}
            # Add any other keys from original result if they exist and are safe to copy
            for key, value in result.items():
                if key != "result":
                    try:
                        summarized_result[key] = copy.deepcopy(value)
                    except (TypeError, ValueError):
                        # Convert unhashable values to strings
                        summarized_result[key] = str(value)
            
            logger.debug(f"Successfully summarized {server_name}.{tool_name} result with investigation context")
            return summarized_result
            
        except Exception as e:
            logger.error(f"Failed to summarize {server_name}.{tool_name} result: {e}")
            raise
    
    def _serialize_conversation_context(self, conversation: LLMConversation) -> str:
        """Serialize LLMConversation into readable context for summarization.
        
        Args:
            conversation: The investigation conversation to serialize
            
        Returns:
            String representation of the conversation context
        """
        context_lines = []
        
        for message in conversation.messages:
            role = message.role.value.upper()
            content = message.content
            
            # Special handling for system messages - extract valuable domain knowledge
            if message.role == MessageRole.SYSTEM:
                content = self._extract_domain_knowledge_from_system_message(content)
            
            # Truncate very long messages to keep context manageable
            if len(content) > 10000:
                content = content[:10000] + "... [truncated]"
            
            context_lines.append(f"{role}: {content}")
        
        return "\n\n".join(context_lines)
    
    def _extract_domain_knowledge_from_system_message(self, system_content: str) -> str:
        """Extract valuable domain knowledge from ReAct system message, filtering out procedural noise.
        
        Args:
            system_content: The content of the system message
            
        Returns:
            Extracted domain knowledge content
        """
        # Import the constant to filter out ReAct formatting instructions
        from tarsy.agents.prompts.templates import REACT_FORMATTING_INSTRUCTIONS
        
        # Remove the ReAct formatting instructions to keep only domain knowledge
        if REACT_FORMATTING_INSTRUCTIONS in system_content:
            domain_content = system_content.split(REACT_FORMATTING_INSTRUCTIONS)[0].strip()
        else:
            # Fallback: take first reasonable chunk if pattern not found
            domain_content = system_content[:1000] + "... [domain knowledge extracted]"
        
        return domain_content
    
    def _truncate_tool_result_if_needed(self, result_text: str) -> str:
        """Truncate tool result content if it exceeds provider-specific limits."""
        # Get provider-specific limit directly from LLM client
        max_tool_result_tokens = self.llm_client.get_max_tool_result_tokens()
        
        # Rough token estimation: ~4 chars per token
        max_chars = max_tool_result_tokens * 4
        
        if len(result_text) > max_chars:
            truncated_text = result_text[:max_chars]
            original_size = len(result_text)
            
            # Add clear truncation marker
            result_text = (
                truncated_text + 
                f"\n\n[TOOL RESULT TRUNCATED - Original size: {original_size:,} chars, "
                f"Truncated to: {max_chars:,} chars for LLM context limits]"
            )
            
            logger.info(
                f"Truncated tool result from {original_size:,} to {len(result_text):,} chars "
                f"(limit: {max_tool_result_tokens:,} tokens)"
            )
        
        return result_text
