"""
Prompt builder for constructing LLM prompts used in agent analysis.

This module centralizes all prompt template logic, making it easier to maintain
and modify prompts without touching business logic in agents.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tarsy.models.agent_execution_result import ChainExecutionContext


@dataclass
class PromptContext:
    """Context data needed for prompt building."""
    agent_name: str
    alert_data: Dict[str, Any]
    runbook_content: str
    mcp_data: Dict[str, Any]
    mcp_servers: List[str]
    server_guidance: str = ""
    agent_specific_guidance: str = ""
    available_tools: Optional[Dict] = None
    iteration_history: Optional[List[Dict]] = None
    current_iteration: Optional[int] = None
    max_iterations: Optional[int] = None
    # Stage context for chain processing
    stage_name: Optional[str] = None
    is_final_stage: bool = False
    previous_stages: Optional[List[str]] = None
    stage_attributed_data: Optional[Dict[str, Any]] = None  # Legacy MCP data with stage attribution
    chain_context: Optional['ChainExecutionContext'] = None  # New AgentExecutionResult-based chain context

class PromptBuilder:
    """
    Centralized prompt builder for all agent operations.
    
    This class handles the construction of all prompts used by agents,
    separating template logic from business logic in agents.
    
    This class is stateless and designed to be shared across agent instances.
    """
    
    def __init__(self):
        """Initialize the prompt builder."""
        pass
    

    
    def build_mcp_tool_selection_prompt(self, context: PromptContext) -> str:
        """
        Build MCP tool selection prompt for initial tool selection.
        
        Args:
            context: Prompt context containing all necessary data
            
        Returns:
            Formatted tool selection prompt
        """
        return f"""# MCP Tool Selection Request

Based on the following alert and runbook, determine which MCP tools should be called to gather additional information.

{context.server_guidance}

## Alert Information
{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Available MCP Tools
{json.dumps(context.available_tools, indent=2)}

## Instructions
Analyze the alert and runbook to determine which MCP tools should be called and with what parameters.
Return a JSON list of tool calls in this format:

```json
[
  {{
    "server": "kubernetes",
    "tool": "get_namespace_status",
    "parameters": {{
      "cluster": "cluster_url_here",
      "namespace": "namespace_name_here"
    }},
    "reason": "Need to check namespace status to understand why it's stuck"
  }}
]
```

Focus on gathering the most relevant information to diagnose the issue described in the alert."""
    
    def build_iterative_mcp_tool_selection_prompt(self, context: PromptContext) -> str:
        """
        Build iterative MCP tool selection prompt for follow-up tool selection.
        
        Args:
            context: Prompt context containing all necessary data
            
        Returns:
            Formatted iterative tool selection prompt
        """
        max_iterations = context.max_iterations or 5
        display_max = max_iterations if context.current_iteration <= max_iterations else context.current_iteration
        
        return f"""# Iterative MCP Tool Selection Request (Iteration {context.current_iteration})

You are analyzing a multi-step runbook. Based on the alert, runbook, and previous iterations, determine if more MCP tools need to be called or if you have sufficient information to complete the analysis.

{context.server_guidance}

## Alert Information
{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Available MCP Tools
{json.dumps(context.available_tools, indent=2)}

## Previous Iterations History
{self._format_iteration_history(context.iteration_history)}

## Instructions
Based on the runbook steps and what has been discovered so far, determine if you need to call more MCP tools or if the analysis can be completed.

**IMPORTANT**: You are currently on iteration {context.current_iteration} of {display_max} maximum iterations. Be judicious about continuing - only continue if you genuinely need critical missing information that prevents completing the analysis.

Return a JSON object in this format:

If more tools are needed:
```json
{{
  "continue": true,
  "reasoning": "Specific explanation of what critical information is missing and why it's needed to complete the runbook steps",
  "tools": [
    {{
      "server": "kubernetes",
      "tool": "tool_name",
      "parameters": {{
        "param1": "value1"
      }},
      "reason": "Why this specific tool call is needed"
    }}
  ]
}}
```

If analysis can be completed:
```json
{{
  "continue": false,  
  "reasoning": "Explanation of what sufficient information has been gathered and why analysis can now be completed"
}}
```

**Default to stopping if you have reasonable data to work with.** The analysis doesn't need to be perfect - it needs to be actionable based on the runbook steps."""
    
    def _build_context_section(self, context: PromptContext) -> str:
        """Build the context section of the prompt."""
        server_list = ", ".join(context.mcp_servers)
        
        return f"""# SRE Alert Analysis Request

You are an expert Site Reliability Engineer (SRE) analyzing a system alert using the {context.agent_name}.
This agent specializes in {server_list} operations and has access to domain-specific tools and knowledge.

Your task is to provide a comprehensive analysis of the incident based on:
1. The alert information
2. The associated runbook
3. Real-time system data from MCP servers

Please provide detailed, actionable insights about what's happening and potential next steps."""
    
    def _build_alert_section(self, alert_data: Dict) -> str:
        """
        Build the alert section of the prompt with flexible data support.
        
        Uses LLM-First Processing approach: displays all alert data as key-value pairs
        for intelligent interpretation by the LLM, rather than hardcoding field expectations.
        """
        if not alert_data:
            return "## Alert Details\n\nNo alert data provided."
        
        alert_text = "## Alert Details\n\n"
        
        # Process all alert data dynamically - LLM-First Processing
        for key, value in alert_data.items():
            # Format the key as human-readable
            formatted_key = key.replace('_', ' ').title()
            
            # Handle different value types intelligently
            if isinstance(value, dict):
                # Nested object - format as JSON for LLM interpretation
                formatted_value = f"\n```json\n{json.dumps(value, indent=2)}\n```"
            elif isinstance(value, list):
                # Array - format as JSON for LLM interpretation
                formatted_value = f"\n```json\n{json.dumps(value, indent=2)}\n```"
            elif isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                # Potential JSON string - try to format it
                try:
                    parsed_json = json.loads(value)
                    formatted_value = f"\n```json\n{json.dumps(parsed_json, indent=2)}\n```"
                except json.JSONDecodeError:
                    # Not valid JSON, treat as regular string
                    formatted_value = str(value)
            elif isinstance(value, str) and '\n' in value:
                # Multi-line string (like YAML) - preserve formatting
                formatted_value = f"\n```\n{value}\n```"
            else:
                # Simple value - display as-is
                formatted_value = str(value) if value is not None else "N/A"
            
            alert_text += f"**{formatted_key}:** {formatted_value}\n"
        
        return alert_text.strip()
    
    def _build_runbook_section(self, runbook_content: str) -> str:
        """Build the runbook section of the prompt."""
        return f"""## Runbook Content
```markdown
<!-- RUNBOOK START -->
{runbook_content if runbook_content else 'No runbook available'}
<!-- RUNBOOK END -->
```"""
    
    def _build_agent_specific_analysis_guidance(self, context: PromptContext) -> str:
        """Build agent-specific analysis guidance."""
        guidance_parts = []
        
        # Add server-specific guidance if available
        if context.server_guidance:
            guidance_parts.append("## Domain-Specific Analysis Guidance")
            guidance_parts.append(context.server_guidance)
        
        # Add custom agent guidance if available
        if context.agent_specific_guidance:
            guidance_parts.append("### Agent-Specific Guidance")
            guidance_parts.append(context.agent_specific_guidance)
        
        return "\n\n".join(guidance_parts) if guidance_parts else ""
    
    def _format_data(self, data) -> str:
        """Format data for display in prompt."""
        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, indent=2, default=str)
            except:
                return str(data)
        return str(data)
    
    def _format_available_tools(self, available_tools: Dict) -> str:
        """Format available tools for display in prompts."""
        if not available_tools:
            return "No tools available."
        return json.dumps(available_tools, indent=2)
    
    def _format_iteration_history(self, iteration_history: List[Dict]) -> str:
        """Format iteration history for display in prompts."""
        if not iteration_history:
            return "No previous iterations."
        
        TOOL_RESULT_TRUNCATION_THRESHOLD = 3000  # Characters before truncating
        
        history_text = ""
        for i, iteration in enumerate(iteration_history, 1):
            history_text += f"### Iteration {i}\n"
            
            # Tools called
            if "tools_called" in iteration and iteration["tools_called"]:
                history_text += "**Tools Called:**\n"
                for tool in iteration["tools_called"]:
                    history_text += f"- {tool.get('server', 'unknown')}.{tool.get('tool', 'unknown')}: {tool.get('reason', 'No reason provided')}\n"
                history_text += "\n"
            
            # Results with actual data content
            if "mcp_data" in iteration and iteration["mcp_data"]:
                history_text += "**Results:**\n"
                for server_name, server_data in iteration["mcp_data"].items():
                    data_count = len(server_data) if isinstance(server_data, list) else 1
                    history_text += f"- **{server_name}**: {data_count} data points collected\n"
                    
                    # Handle both list format (new) and dict format (legacy)
                    if isinstance(server_data, list):
                        # New format: list of results with metadata
                        for item in server_data:
                            tool_name = item.get('tool', 'unknown_tool')
                            params = item.get('parameters', {})
                            
                            # Create a descriptive key for the result
                            if tool_name == 'resources_list' and 'kind' in params or tool_name == 'resources_get' and 'kind' in params:
                                result_key = f"{tool_name}_{params['kind']}_result"
                            else:
                                result_key = f"{tool_name}_result"
                            
                            # Handle both result and error cases
                            if 'result' in item:
                                result = item['result']
                                if result:  # Only show non-empty results
                                    formatted_data = self._format_data({"result": result})
                                    if len(formatted_data) > TOOL_RESULT_TRUNCATION_THRESHOLD:
                                        formatted_data = formatted_data[:TOOL_RESULT_TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                                    history_text += f"  - **{result_key}**:\n```\n{formatted_data}\n```\n"
                            elif 'error' in item:
                                history_text += f"  - **{result_key}_error**: {item['error']}\n"
                    elif isinstance(server_data, dict):
                        # Legacy format: dict with keys like "tool_name_result"
                        for key, value in server_data.items():
                            formatted_data = self._format_data(value)
                            if len(formatted_data) > TOOL_RESULT_TRUNCATION_THRESHOLD:
                                formatted_data = formatted_data[:TOOL_RESULT_TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                            history_text += f"  - **{key}**:\n```\n{formatted_data}\n```\n"
                    else:
                        formatted_data = self._format_data(server_data)
                        if len(formatted_data) > TOOL_RESULT_TRUNCATION_THRESHOLD:
                            formatted_data = formatted_data[:TOOL_RESULT_TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                        history_text += f"```\n{formatted_data}\n```\n"
                history_text += "\n"
            
            # Partial analysis
            if "partial_analysis" in iteration:
                history_text += f"**Partial Analysis:**\n{iteration['partial_analysis']}\n\n"
            
            history_text += "---\n\n"
        
        return history_text.strip()


    def get_general_instructions(self) -> str:
        """
        Get general SRE instructions common to all agents.
        
        Returns:
            General instruction text for system messages
        """
        return """## General SRE Agent Instructions

You are an expert Site Reliability Engineer (SRE) with deep knowledge of:
- Kubernetes and container orchestration
- Cloud infrastructure and services
- Incident response and troubleshooting
- System monitoring and alerting
- GitOps and deployment practices

Analyze alerts thoroughly and provide actionable insights based on:
1. Alert information and context
2. Associated runbook procedures
3. Real-time system data from available tools

Always be specific, reference actual data, and provide clear next steps.
Focus on root cause analysis and sustainable solutions."""

    def get_mcp_tool_selection_system_message(self) -> str:
        """Get system message for MCP tool selection."""
        return "You are an expert SRE analyzing alerts. Based on the alert, runbook, and available MCP tools, determine which tools should be called to gather the necessary information for diagnosis. Return only a valid JSON array with no additional text."
    
    def get_iterative_mcp_tool_selection_system_message(self) -> str:
        """Get system message for iterative MCP tool selection."""
        return "You are an expert SRE analyzing alerts through multi-step runbooks. Based on the alert, runbook, available MCP tools, and previous iteration results, determine what tools should be called next or if the analysis is complete. Return only a valid JSON object with no additional text."
    
    def get_enhanced_react_system_message(self, composed_instructions: str, task_focus: str = "investigation and providing recommendations") -> str:
        """Get enhanced ReAct system message that includes composed instructions from BaseAgent.
        
        This combines the agent's composed instructions (general + MCP server + custom instructions)
        with ReAct-specific formatting rules.
        
        Args:
            composed_instructions: The full composed instructions from BaseAgent._compose_instructions()
            task_focus: Specific focus for this ReAct session
            
        Returns:
            Complete system message with both instructions and ReAct formatting rules
        """
        react_formatting = f"""
🚨 WARNING: NEVER GENERATE FAKE OBSERVATIONS! 🚨
After writing "Action Input:", you MUST stop immediately. The system will provide the "Observation:" for you.
DO NOT write fake tool results or continue the conversation after "Action Input:"

CRITICAL REACT FORMATTING RULES:
Follow the ReAct pattern exactly. You must use this structure:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take (choose from available tools)
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now have sufficient information to provide my analysis
Final Answer: [Complete SRE analysis in structured format - see below]

RESPONSE OPTIONS:
At each step, you have exactly TWO options:

1. Continue investigating: 
   Thought: [your reasoning about what to investigate next]
   Action: [tool to use]
   Action Input: [parameters]

2. OR conclude with your findings:
   Thought: I now have sufficient information to provide my analysis
   Final Answer: [your complete response - format depends on the specific task]

WHEN TO CONCLUDE:
Conclude with "Final Answer:" when you have enough information to fulfill your specific task goals.
You do NOT need perfect information - focus on actionable insights from the data you've collected.

CRITICAL FORMATTING REQUIREMENTS:
1. ALWAYS include colons after section headers: "Thought:", "Action:", "Action Input:"
2. Each section must start on a NEW LINE - never continue on the same line
3. Always add a blank line after "Action Input:" before stopping
4. For Action Input, provide ONLY parameter values (no YAML, no code blocks, no triple backticks)

⚠️ ABSOLUTELY CRITICAL: STOP AFTER "Action Input:" ⚠️
5. STOP immediately after "Action Input:" line - do NOT generate "Observation:"
6. NEVER write fake observations or continue the conversation
7. The system will provide the real "Observation:" - you must NOT generate it yourself
8. After the system provides the observation, then continue with "Thought:" or "Final Answer:"

VIOLATION EXAMPLES (DO NOT DO THIS):
❌ Action Input: apiVersion=v1, kind=Secret, name=my-secret
❌ Observation: kubernetes-server.resources_get: {{"result": "..."}} 
❌ Thought: I have retrieved the data...

CORRECT BEHAVIOR:
✅ Action Input: apiVersion=v1, kind=Secret, name=my-secret
✅ [STOP HERE - SYSTEM WILL PROVIDE OBSERVATION]

NEWLINE FORMATTING IS CRITICAL:
- WRONG: "Thought: I need to check the namespace status first.Action: kubernetes-server.resources_get"
- CORRECT: 
Thought: I need to check the namespace status first.

Action: kubernetes-server.resources_get
Action Input: apiVersion=v1, kind=Namespace, name=superman-dev

EXAMPLE OF CORRECT INVESTIGATION:
Thought: I need to check the namespace status first. This will give me details about why the namespace is stuck in terminating state.

Action: kubernetes-server.resources_get
Action Input: apiVersion=v1, kind=Namespace, name=superman-dev

EXAMPLE OF CONCLUDING PROPERLY:
Thought: I have gathered sufficient information to complete my task. Based on my investigation, I can now provide the requested analysis.

Final Answer: [Provide your complete response in the format appropriate for your specific task - this could be structured analysis, data summary, or stage-specific findings depending on what was requested]

CRITICAL VIOLATIONS TO AVOID:
❌ GENERATING FAKE OBSERVATIONS: Never write "Observation:" yourself - the system provides it
❌ CONTINUING AFTER ACTION INPUT: Stop immediately after "Action Input:" - don't add more content
❌ HALLUCINATING TOOL RESULTS: Don't make up API responses or tool outputs
❌ "Thought" without colon
❌ Action Input with ```yaml or code blocks  
❌ Running sections together on the same line without proper newlines
❌ Providing analysis in non-ReAct format (you MUST use "Final Answer:" to conclude)
❌ Abandoning ReAct format and providing direct structured responses

THE #1 MISTAKE: Writing fake observations and continuing the conversation after Action Input

Focus on {task_focus} for human operators to execute."""
        
        return f"""{composed_instructions}

{react_formatting}"""
    

    # ====================================================================
    # Standard ReAct Framework Methods 
    # ====================================================================

    def _flatten_react_history(self, react_history: List) -> List[str]:
        """
        Utility method to flatten react history and ensure all elements are strings.
        
        This handles cases where react_history contains nested lists from 
        continuation prompts or error handling.
        
        Args:
            react_history: List that may contain strings or nested lists
            
        Returns:
            Flattened list with all elements converted to strings
        """
        flattened_history = []
        for item in react_history:
            if isinstance(item, list):
                flattened_history.extend(str(subitem) for subitem in item)
            else:
                flattened_history.append(str(item))
        return flattened_history

    def build_standard_react_prompt(
        self, context: PromptContext, react_history: Optional[List[str]] = None
    ) -> str:
        """Build standard ReAct prompt for general alert analysis."""
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"

        available_actions = self._format_available_actions(context.available_tools)
        
        # Format the alert analysis question directly
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        question = f"""Analyze this {alert_type} alert and provide actionable recommendations.

{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Previous Stage Data
{self._build_chain_context_section(context)}

## Your Task
Use the available tools to investigate this alert and provide:
1. Root cause analysis
2. Current system state assessment  
3. Specific remediation steps for human operators
4. Prevention recommendations

Be thorough in your investigation before providing the final answer."""

        prompt = (
            "Answer the following question using the available tools.\n\n"
            f"Available tools:\n{available_actions}\n\n"
            f"Question: {question}\n"
            f"{history_text}\n"
            "Begin!"
        )
        return prompt

    def _format_available_actions(self, available_tools: Dict) -> str:
        """Format available tools as ReAct actions."""
        if not available_tools or not available_tools.get("tools"):
            return "No tools available."
        
        actions = []
        for tool in available_tools["tools"]:
            action_name = f"{tool.get('server', 'unknown')}.{tool.get('name', tool.get('tool', 'unknown'))}"
            description = tool.get('description', 'No description available')
            
            # Get parameter info from input schema
            parameters = tool.get('input_schema', {}).get('properties', {})
            if parameters:
                param_desc = ', '.join([f"{k}: {v.get('description', 'no description')}" for k, v in parameters.items()])
                actions.append(f"{action_name}: {description}\n  Parameters: {param_desc}")
            else:
                actions.append(f"{action_name}: {description}")
        
        return '\n'.join(actions)

    def _get_action_names(self, available_tools: Dict) -> List[str]:
        """Get list of action names for the ReAct prompt."""
        if not available_tools or not available_tools.get("tools"):
            return ["No tools available"]
        
        return [f"{tool.get('server', 'unknown')}.{tool.get('name', tool.get('tool', 'unknown'))}" 
                for tool in available_tools["tools"]]

    # ====================================================================
    # ReAct Response Parsing Methods
    # ====================================================================

    def _extract_section_content(self, line: str, prefix: str) -> str:
        """Safely extract content from a line with given prefix, with defensive checks."""
        if not line or not prefix:
            return ""
        
        # Ensure the line is long enough to contain the prefix plus potential content
        if len(line) < len(prefix):
            return ""
        
        # Safely extract content after prefix
        if len(line) > len(prefix):
            return line[len(prefix):].strip()
        
        return ""

    def _is_section_header(self, line: str, section_type: str, found_sections: set) -> bool:
        """Check if line is a valid section header."""
        if not line:
            return False
        
        # For ReAct parsing, allow duplicate actions and thoughts (use latest occurrence)
        # But prevent duplicate final_answer (first one wins)
        if section_type == 'final_answer' and section_type in found_sections:
            return False
            
        if section_type == 'thought':
            return line.startswith('Thought:') or line == 'Thought'
        elif section_type == 'action':
            return line.startswith('Action:')
        elif section_type == 'action_input':
            return line.startswith('Action Input:')
        elif section_type == 'final_answer':
            return line.startswith('Final Answer:')
        
        return False

    def _should_stop_parsing(self, line: str) -> bool:
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

    def _finalize_current_section(self, parsed: Dict[str, Any], current_section: str, content_lines: List[str]) -> None:
        """Safely finalize the current section by joining content lines."""
        if current_section and content_lines is not None:
            new_content = '\n'.join(content_lines).strip()
            # Only overwrite existing content if new content is not empty
            # This handles cases where duplicate sections have empty content
            if new_content or parsed.get(current_section) is None:
                parsed[current_section] = new_content

    def parse_react_response(self, response: str) -> Dict[str, Any]:
        """Parse structured ReAct response into components with robust error handling."""
        # Input validation
        if not response or not isinstance(response, str):
            return {
                'thought': None,
                'action': None,
                'action_input': None,
                'final_answer': None,
                'is_complete': False
            }

        lines = response.strip().split('\n')
        parsed = {
            'thought': None,
            'action': None,
            'action_input': None,
            'final_answer': None,
            'is_complete': False
        }
        
        current_section = None
        content_lines = []  # Always initialize as empty list
        found_sections = set()
        
        try:
            for line in lines:
                # Safely strip line, handle None/empty cases
                line = line.strip() if line else ""
                
                # Skip empty lines when not in a section
                if not line and not current_section:
                    continue
                
                # Check for stop conditions first
                if self._should_stop_parsing(line):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    break
                
                # Handle Final Answer (can appear at any time)
                if self._is_section_header(line, 'final_answer', set()):  # Always allow final_answer
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'final_answer'
                    found_sections.add('final_answer')
                    content_lines = [self._extract_section_content(line, 'Final Answer:')]
                    parsed['is_complete'] = True
                    
                # Handle Thought section  
                elif self._is_section_header(line, 'thought', found_sections):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'thought'
                    found_sections.add('thought')
                    if line.startswith('Thought:'):
                        content_lines = [self._extract_section_content(line, 'Thought:')]
                    else:
                        content_lines = []  # 'Thought' without colon, content on next lines
                    
                # Handle Action section
                elif self._is_section_header(line, 'action', found_sections):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'action'
                    found_sections.add('action')
                    # Clear action_input from found_sections to allow new action_input after new action
                    found_sections.discard('action_input')
                    content_lines = [self._extract_section_content(line, 'Action:')]
                    
                # Handle Action Input section
                elif self._is_section_header(line, 'action_input', found_sections):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'action_input'
                    found_sections.add('action_input')
                    content_lines = [self._extract_section_content(line, 'Action Input:')]
                    
                else:
                    # Only add content if we're in a valid section
                    if current_section and content_lines is not None:
                        content_lines.append(line)
            
            # Handle last section
            self._finalize_current_section(parsed, current_section, content_lines)
            
        except Exception as e:
            # Log the error if needed, but return a safe default structure
            # In a production environment, you might want to add logging here
            pass
        
        return parsed

    def get_react_continuation_prompt(self, context_type: str = "general") -> List[str]:
        """
        Get ReAct continuation prompts for when LLM provides incomplete responses.
        
        Args:
            context_type: Type of ReAct context ("general", "data_collection", "analysis")
            
        Returns:
            List of strings to add to react_history for proper continuation
        """
        prompts = {
            "general": "Observation: Choose ONE option: (1) Continue investigating with 'Thought: [reasoning] Action: [tool] Action Input: [params]' then STOP (do NOT generate fake observations) OR (2) Conclude with 'Thought: I have sufficient information Final Answer: [your analysis]'",
            "data_collection": "Observation: Choose ONE option: (1) Continue data collection with 'Thought: [reasoning] Action: [tool] Action Input: [params]' then STOP (do NOT generate fake observations) OR (2) Conclude with 'Thought: I have sufficient data Final Answer: [data summary]'",
            "analysis": "Observation: Choose ONE option: (1) Continue investigating with 'Thought: [reasoning] Action: [tool] Action Input: [params]' then STOP (do NOT generate fake observations) OR (2) Conclude with 'Thought: I have sufficient information Final Answer: [complete analysis]'"
        }
        
        continuation_message = prompts.get(context_type, prompts["general"])
        return [continuation_message, "Thought:"]
    
    def get_react_error_continuation(self, error_message: str) -> List[str]:
        """
        Get ReAct continuation prompts for error recovery.
        
        Args:
            error_message: The error message to include
            
        Returns:
            List of strings to add to react_history for error recovery
        """
        return [
            f"Observation: Error in reasoning: {error_message}. Please try a different approach.",
            "Thought:"
        ]

    def convert_action_to_tool_call(self, action: str, action_input: str) -> Dict[str, Any]:
        """Convert ReAct Action/Action Input to MCP tool call format."""
        if not action:
            raise ValueError("Action cannot be empty")
        
        if '.' not in action:
            raise ValueError(f"Action must be in format 'server.tool', got: {action}")
        
        server, tool = action.split('.', 1)
        
        # Parse action input (could be JSON, YAML-like, or simple parameters)
        parameters = {}
        action_input = action_input.strip()
        
        try:
            # Try JSON first
            if action_input.startswith('{'):
                parameters = json.loads(action_input)
            else:
                # Handle YAML-like format: "apiVersion: v1, kind: Namespace, name: superman-dev"
                # or key=value format
                for part in action_input.split(','):
                    part = part.strip()
                    if ':' in part and '=' not in part:
                        # YAML-like format (key: value)
                        key, value = part.split(':', 1)
                        parameters[key.strip()] = value.strip()
                    elif '=' in part:
                        # key=value format
                        key, value = part.split('=', 1)
                        parameters[key.strip()] = value.strip()
                    else:
                        # Single parameter without format
                        if not parameters:  # Only if we haven't added anything yet
                            parameters['input'] = action_input
                            break
                        
                # If no structured format detected, treat as single input
                if not parameters:
                    parameters['input'] = action_input
                        
        except json.JSONDecodeError:
            # Fallback: try to parse as key: value or key=value
            for part in action_input.split(','):
                part = part.strip()
                if ':' in part:
                    key, value = part.split(':', 1)
                    parameters[key.strip()] = value.strip()
                elif '=' in part:
                    key, value = part.split('=', 1)
                    parameters[key.strip()] = value.strip()
            
            # Ultimate fallback
            if not parameters:
                parameters['input'] = action_input
        except Exception:
            # Ultimate fallback
            parameters['input'] = action_input
        
        return {
            'server': server,
            'tool': tool,
            'parameters': parameters,
            'reason': f'ReAct Action: {action}'
        }

    def format_observation(self, mcp_data: Dict[str, Any]) -> str:
        """Format MCP data as observation text for ReAct."""
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

    # ====================================================================
    # Chain-Specific ReAct Prompt Methods
    # ====================================================================

    def build_stage_analysis_react_prompt(
        self, context: PromptContext, react_history: Optional[List[str]] = None
    ) -> str:
        """Build ReAct prompt for stage-specific analysis."""
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"

        available_actions = self._format_available_actions(context.available_tools)
        
        # Format stage-specific analysis question directly
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        stage_name = context.stage_name or "analysis"
        question = f"""Investigate this {alert_type} alert and provide stage-specific analysis.

{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Previous Stage Data
{self._build_chain_context_section(context)}

## Your Task: {stage_name.upper()} STAGE
Use available tools to:
1. Collect additional data relevant to this stage
2. Analyze findings in the context of this specific stage
3. Provide stage-specific insights and recommendations

Your Final Answer should include both the data collected and your stage-specific analysis."""

        prompt = (
            "Answer the following question using the available tools.\n\n"
            f"Available tools:\n{available_actions}\n\n"
            f"Question: {question}\n"
            f"{history_text}\n"
            "Begin!"
        )
        return prompt

    def build_final_analysis_prompt(self, context: PromptContext) -> str:
        """Build prompt for final analysis without ReAct format (no tools)."""
        sections = [
            "# Final Analysis Task"
        ]
        
        # Add stage context if available
        if context.stage_name:
            stage_info = f"\n**Stage:** {context.stage_name}"
            if context.is_final_stage:
                stage_info += " (Final Analysis Stage)"
            if context.previous_stages:
                stage_info += f"\n**Previous Stages:** {', '.join(context.previous_stages)}"
            stage_info += "\n"
            sections.append(stage_info)
        
        sections.extend([
            self._build_context_section(context),
            self._build_alert_section(context.alert_data),
            self._build_runbook_section(context.runbook_content)
        ])
        
        # Use unified chain context approach - same as all other strategies
        sections.append(f"## Previous Stage Data\n{self._build_chain_context_section(context)}")
        
        sections.append("""## Instructions
Provide comprehensive final analysis based on ALL collected data:
1. Root cause analysis
2. Impact assessment  
3. Recommended actions
4. Prevention strategies

Do NOT call any tools - use only the provided data.""")
        
        return "\n\n".join(sections)

    def _format_stage_attributed_data(self, stage_attributed_data: Dict[str, Any]) -> str:
        """Format stage-attributed MCP data for clear presentation."""
        if not stage_attributed_data:
            return "No investigation data from previous stages."
        
        sections = []
        for stage_name, stage_data in stage_attributed_data.items():
            sections.append(f"### Data from '{stage_name}' stage:")
            
            if not stage_data:
                sections.append("*No MCP data collected in this stage*")
                continue
            
            for server_name, server_results in stage_data.items():
                if not server_results:
                    continue
                    
                sections.append(f"**{server_name} server:**")
                
                # Handle both list and single result formats
                results_list = server_results if isinstance(server_results, list) else [server_results]
                
                for i, result in enumerate(results_list, 1):
                    if isinstance(result, dict):
                        tool_name = result.get('tool', 'unknown_tool')
                        sections.append(f"  {i}. {tool_name}:")
                        sections.append(f"     {json.dumps(result, indent=6)}")
                    else:
                        sections.append(f"  {i}. {json.dumps(result, indent=4)}")
                sections.append("")  # Add spacing between servers
        
        return "\n".join(sections)
    
    def _build_chain_context_section(self, context: PromptContext) -> str:
        """
        Build previous stage data section using chain context data.
        """
        # Use new ChainExecutionContext if available
        if context.chain_context and context.chain_context.stage_results:
            return context.chain_context.get_formatted_context()
       
        # No previous stage data available
        return "No previous stage data available."


# Shared instance since PromptBuilder is stateless
_shared_prompt_builder = PromptBuilder()


def get_prompt_builder() -> PromptBuilder:
    """Get the shared PromptBuilder instance."""
    return _shared_prompt_builder 