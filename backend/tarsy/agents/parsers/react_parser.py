"""
Type-safe ReAct response parser that consolidates all parsing logic.

This module replaces dict-based parsing from builders.py with proper types,
providing validation and type safety for ReAct response processing.
"""

import json
import logging
import re
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


class ResponseType(Enum):
    """Type of ReAct response parsed from LLM output."""
    THOUGHT_ACTION = "thought_action"
    FINAL_ANSWER = "final_answer"
    MALFORMED = "malformed"


class ToolCall(BaseModel):
    """Type-safe tool call representation with validation."""
    server: str = Field(..., min_length=1, description="MCP server name")
    tool: str = Field(..., min_length=1, description="Tool name")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    reason: str = Field(..., description="Reason for this tool call")

    @field_validator('server')
    @classmethod
    def validate_server_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Server name cannot be empty")
        return v.strip()

    @field_validator('tool')
    @classmethod
    def validate_tool_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Tool name cannot be empty")
        return v.strip()


class ReActResponse(BaseModel):
    """Type-safe ReAct response representation with validation."""
    response_type: ResponseType = Field(..., description="Type of response parsed")
    thought: Optional[str] = Field(None, description="Reasoning thought (optional - LLMs sometimes skip this)")
    
    # For THOUGHT_ACTION responses
    action: Optional[str] = None
    action_input: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    
    # For FINAL_ANSWER responses
    final_answer: Optional[str] = None
    
    @property
    def is_final_answer(self) -> bool:
        """Check if this is a final answer response."""
        return self.response_type == ResponseType.FINAL_ANSWER
    
    @property  
    def has_action(self) -> bool:
        """Check if this response contains a valid action."""
        return self.response_type == ResponseType.THOUGHT_ACTION and self.tool_call is not None
    
    @property
    def is_malformed(self) -> bool:
        """Check if this response is malformed."""
        return self.response_type == ResponseType.MALFORMED


class ReActParser:
    """
    Type-safe ReAct response parser that consolidates all parsing logic.
    
    Replaces dict-based parsing from builders.py with proper types.
    """
    
    @staticmethod
    def parse_response(response: str) -> ReActResponse:
        """
        Parse LLM response into type-safe ReActResponse object.
        
        Consolidates logic from builders.parse_react_response() with proper validation.
        
        Returns:
            ReActResponse with automatic validation and type checking.
            For malformed inputs, returns ReActResponse with ResponseType.MALFORMED
            instead of raising exceptions, providing consistent error handling.
        """
        if not response or not isinstance(response, str):
            return ReActResponse(response_type=ResponseType.MALFORMED, thought=None)
        
        # Parse sections using existing logic from builders.py
        sections = ReActParser._extract_sections(response)
        
        # Check for final answer first
        if sections.get('final_answer'):
            return ReActResponse(
                response_type=ResponseType.FINAL_ANSWER,
                thought=sections.get('thought'),
                final_answer=sections['final_answer']
            )
        
        # Check for action (with or without thought - LLMs sometimes skip thought)
        action = sections.get('action')
        action_input = sections.get('action_input')
        if action and action_input is not None:  # Allow empty action_input for tools with no parameters
            try:
                tool_call = ReActParser._convert_to_tool_call(action, action_input)
                return ReActResponse(
                    response_type=ResponseType.THOUGHT_ACTION,
                    thought=sections.get('thought'),  # Optional - might be None
                    action=action,
                    action_input=action_input,
                    tool_call=tool_call
                )
            except (ValueError, ValidationError) as e:
                # Log the error and return malformed response
                logger.error(f"Invalid action format: {str(e)}")
                return ReActResponse(response_type=ResponseType.MALFORMED, thought=None)
        
        # Malformed response
        return ReActResponse(response_type=ResponseType.MALFORMED, thought=None)
    
    @staticmethod
    def _extract_sections(response: str) -> Dict[str, Optional[str]]:
        """
        Extract ReAct sections from response text.
        
        Moved from builders.py with improved error handling.
        """
        if not response or not isinstance(response, str):
            return {}

        lines = response.strip().split('\n')
        parsed: Dict[str, Optional[str]] = {
            'thought': None,
            'action': None,
            'action_input': None,
            'final_answer': None
        }
        
        current_section: Optional[str] = None
        content_lines: list[str] = []
        found_sections: set[str] = set()
        
        try:
            for line in lines:
                # Safely strip line, handle None/empty cases
                line = line.strip() if line else ""
                
                # Skip empty lines when not in a section
                if not line and not current_section:
                    continue
                
                # Check for stop conditions first
                if ReActParser._should_stop_parsing(line):
                    ReActParser._finalize_current_section(parsed, current_section, content_lines)
                    break
                
                # Handle Final Answer (can appear at any time)
                if ReActParser._is_section_header(line, 'final_answer', found_sections):
                    ReActParser._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'final_answer'
                    found_sections.add('final_answer')
                    content_lines = [ReActParser._extract_section_content(line, 'Final Answer:')]
                    
                # Handle Thought section  
                elif ReActParser._is_section_header(line, 'thought', found_sections):
                    ReActParser._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'thought'
                    found_sections.add('thought')
                    if line.startswith('Thought:'):
                        thought_content = ReActParser._extract_section_content(line, 'Thought:')
                        # Check if there's a mid-line Action in the thought content
                        # This handles cases like "Thought: Some text.Action: tool"
                        if ReActParser._has_midline_action(thought_content):
                            # Split at the Action boundary
                            match = re.search(r'[.!?][`\s*]*Action:', thought_content)
                            if match:
                                # Store thought up to the action
                                parsed['thought'] = thought_content[:match.start() + 1].strip()  # Keep the punctuation
                                # Process the rest as a new line starting with Action:
                                remaining = thought_content[match.start() + 1:].strip()  # Remove leading punctuation
                                # Re-process this as if it's the Action: line
                                # We'll handle it in the next iteration by treating it as if Action: started the line
                                # For now, just extract what we can
                                action_match = re.search(r'Action:\s*(.+)', remaining)
                                if action_match:
                                    parsed['action'] = action_match.group(1).strip()
                                    found_sections.add('action')
                                current_section = None  # Reset to look for Action Input on next line
                                content_lines = []
                            else:
                                content_lines = [thought_content]
                        else:
                            content_lines = [thought_content]
                    else:
                        content_lines = []  # 'Thought' without colon, content on next lines
                    
                # Handle Action section
                elif ReActParser._is_section_header(line, 'action', found_sections):
                    ReActParser._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'action'
                    found_sections.add('action')
                    # Clear action_input from found_sections to allow new action_input after new action
                    found_sections.discard('action_input')
                    content_lines = [ReActParser._extract_section_content(line, 'Action:')]
                    
                # Handle Action Input section
                elif ReActParser._is_section_header(line, 'action_input', found_sections):
                    ReActParser._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'action_input'
                    found_sections.add('action_input')
                    content_lines = [ReActParser._extract_section_content(line, 'Action Input:')]
                    
                else:
                    # Only add content if we're in a valid section
                    if current_section and content_lines is not None:
                        content_lines.append(line)
            
            # Handle last section
            ReActParser._finalize_current_section(parsed, current_section, content_lines)
            
        except Exception as e:
            # Log the error for debugging purposes while returning partial parse state
            logger.error(
                f"Exception occurred while parsing ReAct response, returning partial results: {str(e)}", 
                exc_info=True
            )
            # Return the partial parse state that was built so far
            return parsed
        
        return parsed
    
    @staticmethod
    def _extract_section_content(line: str, prefix: str) -> str:
        """
        Safely extract content from a line with given prefix.
        
        Handles both standard format (prefix at line start) and fallback format
        (prefix mid-line after sentence boundary).
        
        Args:
            line: The line containing the prefix
            prefix: The section prefix to find (e.g., "Action:", "Action Input:")
            
        Returns:
            Content after the prefix, stripped of leading/trailing whitespace
        """
        if not line or not prefix:
            return ""
        
        # Find the prefix in the line (handles both line-start and mid-line cases)
        idx = line.find(prefix)
        if idx == -1:
            return ""
        
        # Extract everything after the prefix
        content = line[idx + len(prefix):].strip()
        return content

    @staticmethod
    def _is_section_header(
        line: str, section_type: str, found_sections: set[str]
    ) -> bool:
        """
        Check if line is a valid section header with 3-tier detection:
        
        Tier 1: Standard format (starts with header) - preferred
        Tier 2: Detect Final Answer to rule out confusion
        Tier 3: Fallback for Action only - detect mid-line after sentence boundary
        
        This handles cases where LLMs generate text like:
        "I will get the namespace.Action: kubernetes-server.resources_get"
        """
        if not line:
            return False
        
        # For ReAct parsing, allow duplicate actions and thoughts (use latest occurrence)
        # But prevent duplicate final_answer (first one wins)
        if section_type == 'final_answer' and section_type in found_sections:
            return False
        
        # TIER 1: Standard format check (line starts with section header)
        if section_type == 'thought':
            if line.startswith('Thought:') or line == 'Thought':
                return True
        elif section_type == 'action':
            if line.startswith('Action:'):
                return True
        elif section_type == 'action_input':
            if line.startswith('Action Input:'):
                return True
        elif section_type == 'final_answer':
            if line.startswith('Final Answer:'):
                return True
        
        # TIER 2: If we're looking for final_answer and didn't find it, stop here
        # This ensures we won't confuse mid-line "Action:" with "Final Answer:"
        if section_type == 'final_answer':
            return False
        
        # TIER 3: Fallback detection for Action only - handle malformed LLM output
        # Look for "Action:" appearing mid-line after sentence-ending punctuation
        # This is safe because:
        # - We already ruled out Final Answer confusion in Tier 2
        # - Requires sentence boundary (. ! ? followed by Action:)
        # - Case-sensitive (won't match lowercase "action:")
        # - Won't match narrative like "The action: check logs" (no sentence boundary before it)
        if section_type == 'action' and 'Action:' in line:
            # Match: sentence ending (. ! ?) + optional space/backtick/closing-markup + "Action:"
            # Examples that match: ".Action:", "!Action:", ". Action:", ".`Action:", ".**Action:"
            # Examples that DON'T match: "action:", "an Action:", "take action: check"
            pattern = r'[.!?][`\s*]*Action:'
            if re.search(pattern, line):
                logger.info(
                    f"Parser fallback: detected mid-line 'Action:' after sentence boundary in: "
                    f"{line[:80]}{'...' if len(line) > 80 else ''}"
                )
                return True
        
        # TIER 3: Fallback for Action Input only if Action was already found
        # This handles cases where LLM doesn't put newline before "Action Input:"
        if section_type == 'action_input' and 'Action Input:' in line:
            # Only trigger if we've already seen an Action (prevent false positives)
            if 'action' in found_sections:
                # Similar pattern but for Action Input
                pattern = r'[.!?][`\s*]*Action Input:'
                if re.search(pattern, line):
                    logger.info(
                        f"Parser fallback: detected mid-line 'Action Input:' after sentence boundary"
                    )
                    return True
        
        return False
    
    @staticmethod
    def _has_midline_action(text: str) -> bool:
        """Check if text contains a mid-line Action: after sentence boundary."""
        if not text or 'Action:' not in text:
            return False
        pattern = r'[.!?][`\s*]*Action:'
        return bool(re.search(pattern, text))

    @staticmethod
    def _should_stop_parsing(line: str) -> bool:
        """Check if we should stop parsing due to fake content markers."""
        if not line:
            return False
        
        # Stop parsing on fake/hallucinated observations that LLM generates
        # But NOT on legitimate continuation prompts that are part of the conversation
        if line.startswith('[Based on'):
            return True
        
        # Only stop on observations that look like hallucinated tool results
        # Continuation prompts like "Please specify what Action..." should not stop parsing
        if line.startswith('Observation:'):
            # Don't stop if this looks like a continuation prompt
            if 'Please specify' in line or 'what Action you want to take' in line:
                return False
            # Don't stop if this looks like an error continuation 
            if 'Error in reasoning' in line:
                return False
            # This appears to be a real/hallucinated observation - stop parsing
            return True
            
        return False

    @staticmethod
    def _finalize_current_section(
        parsed: Dict[str, Any], 
        current_section: Optional[str], 
        content_lines: list[str]
    ) -> None:
        """Safely finalize the current section by joining content lines."""
        if current_section and content_lines is not None:
            new_content = '\n'.join(content_lines).strip()
            # Only overwrite existing content if new content is not empty
            # This handles cases where duplicate sections have empty content
            if new_content or parsed.get(current_section) is None:
                parsed[current_section] = new_content
    
    @staticmethod
    def _convert_to_tool_call(action: str, action_input: str) -> ToolCall:
        """
        Convert action + input to type-safe ToolCall.
        
        Moved from builders.convert_action_to_tool_call() with proper return type.
        """
        # Trim whitespace from action string before validation
        action = action.strip() if action else ""
        
        # Validate action is not empty and contains a dot
        if not action:
            raise ValueError("Action cannot be empty or whitespace-only")
        
        if '.' not in action:
            raise ValueError(f"Action must contain a dot separator (server.tool format): '{action}'")
        
        # Split by first dot and validate both parts
        server, tool = action.split('.', 1)
        
        # Validate server part is not empty
        if not server or not server.strip():
            raise ValueError(f"Server name cannot be empty in action: '{action}'")
        
        # Validate tool part is not empty  
        if not tool or not tool.strip():
            raise ValueError(f"Tool name cannot be empty in action: '{action}'")
        
        # Trim whitespace from server and tool parts
        server = server.strip()
        tool = tool.strip()
        
        # Parse parameters (moved from builders.py logic)
        parameters = ReActParser._parse_action_parameters(action_input)
        
        return ToolCall(
            server=server,
            tool=tool,
            parameters=parameters,
            reason=f"ReAct:{server}.{tool}"
        )
    
    @staticmethod
    def _parse_action_parameters(action_input: str) -> Dict[str, Any]:
        """
        Parse action input parameters from various formats.
        
        Supports:
        - JSON format: {"key": "value", "key2": "value2"}
        - Comma-separated: key: value, key2: value2
        - Newline-separated: key: value\nkey2: value2
        - Key=value format: key=value, key2=value2
        - Mixed separators (commas and newlines)
        
        Moved from builders.convert_action_to_tool_call() logic.
        """
        parameters: Dict[str, Any] = {}
        action_input = action_input.strip() if action_input else ""
        
        if not action_input:
            return parameters
        
        try:
            # Try JSON first - attempt to parse any valid JSON format
            parsed_json = json.loads(action_input)
            # Ensure result is always a dict - wrap non-dict JSON in {'input': value}
            if isinstance(parsed_json, dict):
                parameters = parsed_json
            else:
                parameters = {'input': parsed_json}
        except json.JSONDecodeError:
            # Fallback: Handle multiple formats
            # Split on both commas AND newlines to handle both separators
            # Replace newlines with commas first for unified processing
            normalized_input = action_input.replace('\n', ',')
            parts = [p.strip() for p in normalized_input.split(',') if p.strip()]
            
            for part in parts:
                if ':' in part and '=' not in part:
                    # YAML-like format (key: value)
                    key, value = part.split(':', 1)
                    parameters[key.strip()] = ReActParser._convert_parameter_value(value.strip())
                elif '=' in part:
                    # key=value format
                    key, value = part.split('=', 1)
                    parameters[key.strip()] = ReActParser._convert_parameter_value(value.strip())
                else:
                    # Single parameter without format
                    if not parameters:  # Only if we haven't added anything yet
                        parameters['input'] = action_input
                        break
                    
            # If no structured format detected, treat as single input
            if not parameters:
                parameters['input'] = action_input
        except Exception:
            # Ultimate fallback
            parameters['input'] = action_input
        
        return parameters
    
    @staticmethod
    def _convert_parameter_value(value: str) -> Any:
        """
        Convert a string parameter value to its appropriate type.
        
        Handles booleans, integers, floats, and keeps strings as strings.
        This is essential for MCP tool calls that expect specific types.
        """
        value = value.strip()
        
        # Handle boolean values
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return False
        
        # Handle null/None values
        if value.lower() in ('null', 'none'):
            return None
        
        # Try integer conversion
        try:
            # Check if it looks like an integer (no decimal point)
            if '.' not in value:
                return int(value)
        except ValueError:
            pass
        
        # Try float conversion
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string if no other type matches
        return value
    
    @staticmethod
    def get_continuation_prompt(context_type: str = "general") -> str:
        """
        Get continuation prompt for malformed responses.
        
        Moved from builders.get_react_continuation_prompt() with simplified return type.
        """
        prompts = {
            "general": (
                "Choose ONE option: (1) Continue investigating with "
                "'Thought: [reasoning]\\n Action: [tool]\\n Action Input: [params]' then STOP "
                "(do NOT generate fake observations) OR (2) Conclude with "
                "'Thought: I have sufficient information\\n Final Answer: [your analysis]'"
            ),
            "data_collection": (
                "Choose ONE option: (1) Continue data collection with "
                "'Thought: [reasoning]\\n Action: [tool]\\n Action Input: [params]' then STOP "
                "(do NOT generate fake observations) OR (2) Conclude with "
                "'Thought: I have sufficient data\\n Final Answer: [data summary]'"
            ),
            "analysis": (
                "Choose ONE option: (1) Continue investigating with "
                "'Thought: [reasoning]\\n Action: [tool]\\n Action Input: [params]' then STOP "
                "(do NOT generate fake observations) OR (2) Conclude with "
                "'Thought: I have sufficient information\\n Final Answer: [complete analysis]'"
            )
        }
        return prompts.get(context_type, prompts["general"])
    
    @staticmethod
    def get_format_correction_reminder() -> str:
        """
        Get brief format reminder when LLM generates malformed response.
        
        This reminder is appended to the user message AFTER removing the malformed assistant response.
        Since the LLM won't see its malformed response, we don't mention any "error" - we just
        emphasize the critical format rules as if this is the first time seeing the request.
        """
        return """
IMPORTANT: Please follow the exact ReAct format:

1. Use colons: "Thought:", "Action:", "Action Input:"
2. Start each section on a NEW LINE
3. Stop after Action Input - the system provides Observations

Required structure:
Thought: [your reasoning]
Action: [tool name]
Action Input: [parameters]"""
    
    @staticmethod  
    def format_observation(mcp_data: Dict[str, Any]) -> str:
        """
        Format MCP tool results as observation text.
        
        Moved from builders.format_observation().
        """
        if not mcp_data:
            return "No data returned from the action."
        
        observations = []
        for server, results in mcp_data.items():
            if isinstance(results, list):
                for result in results:
                    if 'result' in result and result['result']:
                        # Format the result nicely
                        if isinstance(result['result'], dict):
                            formatted_result = json.dumps(result['result'], indent=2)
                        else:
                            formatted_result = str(result['result'])
                        observations.append(f"{server}.{result.get('tool', 'unknown')}: {formatted_result}")
                    elif 'error' in result:
                        observations.append(f"{server}.{result.get('tool', 'unknown')} error: {result['error']}")
            else:
                # Legacy format
                observations.append(f"{server}: {json.dumps(results, indent=2)}")
        
        return '\n'.join(observations) if observations else "Action completed but no specific data returned."
