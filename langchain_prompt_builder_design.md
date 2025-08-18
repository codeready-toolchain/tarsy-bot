# LangChain PromptBuilder Design Document

## Architecture Overview

Replace current `PromptBuilder` with LangChain-based template system using component composition pattern.

### Dependencies
```bash
uv add langchain-core
```

### File Structure
```
backend/tarsy/agents/prompt_templates/
├── __init__.py
├── components.py           # Reusable template components
├── builders.py            # Main builder classes
└── templates.py           # LangChain template definitions
```

## Core Components

### 1. Template Components (`components.py`)
```python
from langchain_core.prompts import PromptTemplate
from typing import Dict, Any, List, Optional
import json

class AlertSectionTemplate:
    """Formats alert data with intelligent type handling."""
    
    template = PromptTemplate.from_template("""## Alert Details

{formatted_alert_data}""")
    
    def format(self, alert_data: Dict[str, Any]) -> str:
        formatted_data = self._format_alert_entries(alert_data)
        return self.template.format(formatted_alert_data=formatted_data)
    
    def _format_alert_entries(self, alert_data: Dict[str, Any]) -> str:
        if not alert_data:
            return "No alert data provided."
        
        lines = []
        for key, value in alert_data.items():
            formatted_key = key.replace('_', ' ').title()
            formatted_value = self._format_value(value)
            lines.append(f"**{formatted_key}:** {formatted_value}")
        
        return "\n".join(lines)
    
    def _format_value(self, value) -> str:
        """Format value with type-appropriate formatting."""
        if isinstance(value, dict):
            return f"\n```json\n{json.dumps(value, indent=2)}\n```"
        elif isinstance(value, list):
            return f"\n```json\n{json.dumps(value, indent=2)}\n```"
        elif isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
            try:
                parsed = json.loads(value)
                return f"\n```json\n{json.dumps(parsed, indent=2)}\n```"
            except json.JSONDecodeError:
                return str(value)
        elif isinstance(value, str) and '\n' in value:
            return f"\n```\n{value}\n```"
        else:
            return str(value) if value is not None else "N/A"

class RunbookSectionTemplate:
    """Formats runbook content."""
    
    template = PromptTemplate.from_template("""## Runbook Content
```markdown
<!-- RUNBOOK START -->
{runbook_content}
<!-- RUNBOOK END -->
```""")
    
    def format(self, runbook_content: str) -> str:
        content = runbook_content if runbook_content else 'No runbook available'
        return self.template.format(runbook_content=content)


class ChainContextSectionTemplate:
    """Formats chain context data."""
    
    def format(self, context) -> str:
        if hasattr(context, 'chain_context') and context.chain_context and context.chain_context.stage_results:
            return context.chain_context.get_formatted_context()
        return "No previous stage data available."
```

### 2. LangChain Templates (`templates.py`)
```python
from langchain_core.prompts import PromptTemplate

# ReAct System Message Template
REACT_SYSTEM_TEMPLATE = PromptTemplate.from_template("""{composed_instructions}

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

Focus on {task_focus} for human operators to execute.""")

# Standard ReAct Prompt Template
STANDARD_REACT_PROMPT_TEMPLATE = PromptTemplate.from_template("""Answer the following question using the available tools.

Available tools:
{available_actions}

Question: {question}

{history_text}
Begin!""")

# Analysis Question Template
ANALYSIS_QUESTION_TEMPLATE = PromptTemplate.from_template("""Analyze this {alert_type} alert and provide actionable recommendations.

{alert_section}

{runbook_section}

## Previous Stage Data
{chain_context}

## Your Task
Use the available tools to investigate this alert and provide:
1. Root cause analysis
2. Current system state assessment  
3. Specific remediation steps for human operators
4. Prevention recommendations

Be thorough in your investigation before providing the final answer.""")

# Stage Analysis Question Template
STAGE_ANALYSIS_QUESTION_TEMPLATE = PromptTemplate.from_template("""Investigate this {alert_type} alert and provide stage-specific analysis.

{alert_section}

{runbook_section}

## Previous Stage Data
{chain_context}

## Your Task: {stage_name} STAGE
Use available tools to:
1. Collect additional data relevant to this stage
2. Analyze findings in the context of this specific stage
3. Provide stage-specific insights and recommendations

Your Final Answer should include both the data collected and your stage-specific analysis.""")

# Final Analysis Prompt Template
FINAL_ANALYSIS_PROMPT_TEMPLATE = PromptTemplate.from_template("""# Final Analysis Task

{stage_info}

{context_section}

{alert_section}

{runbook_section}

## Previous Stage Data
{chain_context}

## Instructions
Provide comprehensive final analysis based on ALL collected data:
1. Root cause analysis
2. Impact assessment  
3. Recommended actions
4. Prevention strategies

Do NOT call any tools - use only the provided data.""")

# Context Section Template
CONTEXT_SECTION_TEMPLATE = PromptTemplate.from_template("""# SRE Alert Analysis Request

You are an expert Site Reliability Engineer (SRE) analyzing a system alert using the {agent_name}.
This agent specializes in {server_list} operations and has access to domain-specific tools and knowledge.

Your task is to provide a comprehensive analysis of the incident based on:
1. The alert information
2. The associated runbook
3. Real-time system data from MCP servers

Please provide detailed, actionable insights about what's happening and potential next steps.""")

# MCP Tool Selection Template
MCP_TOOL_SELECTION_TEMPLATE = PromptTemplate.from_template("""# MCP Tool Selection Request

Based on the following alert and runbook, determine which MCP tools should be called to gather additional information.

{server_guidance}

## Alert Information
{alert_section}

{runbook_section}

## Available MCP Tools
{available_tools}

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

Focus on gathering the most relevant information to diagnose the issue described in the alert.""")

# Iterative MCP Tool Selection Template
ITERATIVE_MCP_TOOL_SELECTION_TEMPLATE = PromptTemplate.from_template("""# Iterative MCP Tool Selection Request (Iteration {current_iteration})

You are analyzing a multi-step runbook. Based on the alert, runbook, and previous iterations, determine if more MCP tools need to be called or if you have sufficient information to complete the analysis.

{server_guidance}

## Alert Information
{alert_section}

{runbook_section}

## Available MCP Tools
{available_tools}

## Previous Iterations History
{iteration_history}

## Instructions
Based on the runbook steps and what has been discovered so far, determine if you need to call more MCP tools or if the analysis can be completed.

**IMPORTANT**: You are currently on iteration {current_iteration} of {max_iterations} maximum iterations. Be judicious about continuing - only continue if you genuinely need critical missing information that prevents completing the analysis.

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

**Default to stopping if you have reasonable data to work with.** The analysis doesn't need to be perfect - it needs to be actionable based on the runbook steps.""")
```

### 3. Main Builder Class (`builders.py`)
```python
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from .components import (
    AlertSectionTemplate, 
    RunbookSectionTemplate, 
    ChainContextSectionTemplate
)
from .templates import *
import json

if TYPE_CHECKING:
    from tarsy.models.agent_execution_result import ChainExecutionContext

class LangChainPromptBuilder:
    """LangChain-based prompt builder with template composition."""
    
    def __init__(self):
        # Initialize component templates
        self.alert_component = AlertSectionTemplate()
        self.runbook_component = RunbookSectionTemplate()
        self.chain_context_component = ChainContextSectionTemplate()
    
    # ============ Main Prompt Building Methods ============
    
    def build_standard_react_prompt(self, context, react_history: Optional[List[str]] = None) -> str:
        """Build standard ReAct prompt using templates."""
        # Build question components
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        chain_context = self.chain_context_component.format(context)
        
        # Build question
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        question = ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=alert_type,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
        
        # Build final prompt
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"
        
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(context.available_tools),
            question=question,
            history_text=history_text
        )
    
    def build_stage_analysis_react_prompt(self, context, react_history: Optional[List[str]] = None) -> str:
        """Build ReAct prompt for stage-specific analysis."""
        # Build question components
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        chain_context = self.chain_context_component.format(context)
        
        # Build question
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        stage_name = context.stage_name or "analysis"
        question = STAGE_ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=alert_type,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context,
            stage_name=stage_name.upper()
        )
        
        # Build final prompt
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"
        
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(context.available_tools),
            question=question,
            history_text=history_text
        )
    
    def build_final_analysis_prompt(self, context) -> str:
        """Build prompt for final analysis without ReAct format."""
        stage_info = ""
        if context.stage_name:
            stage_info = f"\n**Stage:** {context.stage_name}"
            if context.is_final_stage:
                stage_info += " (Final Analysis Stage)"
            if context.previous_stages:
                stage_info += f"\n**Previous Stages:** {', '.join(context.previous_stages)}"
            stage_info += "\n"
        
        context_section = self._build_context_section(context)
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        chain_context = self.chain_context_component.format(context)
        
        return FINAL_ANALYSIS_PROMPT_TEMPLATE.format(
            stage_info=stage_info,
            context_section=context_section,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
    
    def build_mcp_tool_selection_prompt(self, context) -> str:
        """Build MCP tool selection prompt."""
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        return MCP_TOOL_SELECTION_TEMPLATE.format(
            server_guidance=context.server_guidance,
            alert_section=alert_section,
            runbook_section=runbook_section,
            available_tools=json.dumps(context.available_tools, indent=2)
        )
    
    def build_iterative_mcp_tool_selection_prompt(self, context) -> str:
        """Build iterative MCP tool selection prompt."""
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        max_iterations = context.max_iterations or 5
        display_max = max_iterations if context.current_iteration <= max_iterations else context.current_iteration
        
        return ITERATIVE_MCP_TOOL_SELECTION_TEMPLATE.format(
            current_iteration=context.current_iteration,
            server_guidance=context.server_guidance,
            alert_section=alert_section,
            runbook_section=runbook_section,
            available_tools=json.dumps(context.available_tools, indent=2),
            iteration_history=self._format_iteration_history(context.iteration_history),
            max_iterations=display_max
        )
    
    # ============ System Message Methods ============
    
    def get_enhanced_react_system_message(self, composed_instructions: str, task_focus: str = "investigation and providing recommendations") -> str:
        """Get enhanced ReAct system message using template."""
        return REACT_SYSTEM_TEMPLATE.format(
            composed_instructions=composed_instructions,
            task_focus=task_focus
        )
    
    def get_general_instructions(self) -> str:
        """Get general SRE instructions."""
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
    
    # ============ Helper Methods (Keep Current Logic) ============
    
    def _build_context_section(self, context) -> str:
        """Build the context section using template."""
        server_list = ", ".join(context.mcp_servers)
        return CONTEXT_SECTION_TEMPLATE.format(
            agent_name=context.agent_name,
            server_list=server_list
        )
    
    def _build_agent_specific_analysis_guidance(self, context) -> str:
        """Build agent-specific analysis guidance."""
        guidance_parts = []
        
        if context.server_guidance:
            guidance_parts.append("## Domain-Specific Analysis Guidance")
            guidance_parts.append(context.server_guidance)
        
        if context.agent_specific_guidance:
            guidance_parts.append("### Agent-Specific Guidance")
            guidance_parts.append(context.agent_specific_guidance)
        
        return "\n\n".join(guidance_parts) if guidance_parts else ""
    
    def _build_analysis_instructions(self) -> str:
        """Build the analysis instructions section."""
        return """## Analysis Instructions

Please provide your analysis in the following structured format:

# 🚨 1. QUICK SUMMARY
**Provide a brief, concrete summary (2-3 sentences maximum):**
- What specific resource is affected (include **name**, **type**, **namespace** if applicable)
- What exactly is wrong with it
- Root cause in simple terms

---

# ⚡ 2. RECOMMENDED ACTIONS

## 🔧 Immediate Fix Actions (if any):
**List specific commands that could potentially resolve the issue, in order of priority:**
- Command 1. Explanation of what this does
```command
command here
```
- Command 2. Explanation of what this does
```command
command here
```

## 🔍 Investigation Actions (if needed):
**List commands for further investigation:**
- Command 1. What information this will provide
```command
command here
```
- Command 2. What information this will provide
```command
command here
```

---

## 3. DETAILED ANALYSIS

### Root Cause Analysis:
- What is the primary cause of this alert?
- What evidence from the system data supports this conclusion?
- Technical details and context

### Current System State:
- Detailed state of affected systems and resources
- Any blocked processes or dependencies preventing resolution
- Related system dependencies and interactions

### Impact Assessment:
- Current impact on system functionality
- Potential escalation scenarios
- Affected services or users

### Prevention Measures:
- How can this issue be prevented in the future?
- Monitoring improvements needed
- Process or automation recommendations

### Additional Context:
- Related systems that should be monitored
- Historical patterns or similar incidents
- Any other relevant technical details

Please be specific and reference the actual data provided. Use exact resource names, namespaces, and status information from the system data."""
    
    def _format_available_actions(self, available_tools: Dict) -> str:
        """Format available tools as ReAct actions."""
        if not available_tools or not available_tools.get("tools"):
            return "No tools available."
        
        actions = []
        for tool in available_tools["tools"]:
            action_name = f"{tool.get('server', 'unknown')}.{tool.get('name', tool.get('tool', 'unknown'))}"
            description = tool.get('description', 'No description available')
            
            parameters = tool.get('input_schema', {}).get('properties', {})
            if parameters:
                param_desc = ', '.join([f"{k}: {v.get('description', 'no description')}" for k, v in parameters.items()])
                actions.append(f"{action_name}: {description}\n  Parameters: {param_desc}")
            else:
                actions.append(f"{action_name}: {description}")
        
        return '\n'.join(actions)
    
    def _flatten_react_history(self, react_history: List) -> List[str]:
        """Utility method to flatten react history and ensure all elements are strings."""
        flattened_history = []
        for item in react_history:
            if isinstance(item, list):
                flattened_history.extend(str(subitem) for subitem in item)
            else:
                flattened_history.append(str(item))
        return flattened_history
    
    def _format_data(self, data) -> str:
        """Format data for display in prompts."""
        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, indent=2, default=str)
            except:
                return str(data)
        return str(data)
    
    def _format_iteration_history(self, iteration_history: List[Dict]) -> str:
        """Format iteration history for display in prompts."""
        if not iteration_history:
            return "No previous iterations."
        
        TRUNCATION_THRESHOLD = 3000
        history_text = ""
        
        for i, iteration in enumerate(iteration_history, 1):
            history_text += f"### Iteration {i}\n"
            
            if "tools_called" in iteration and iteration["tools_called"]:
                history_text += "**Tools Called:**\n"
                for tool in iteration["tools_called"]:
                    history_text += f"- {tool.get('server', 'unknown')}.{tool.get('tool', 'unknown')}: {tool.get('reason', 'No reason provided')}\n"
                history_text += "\n"
            
            if "mcp_data" in iteration and iteration["mcp_data"]:
                history_text += "**Results:**\n"
                for server_name, server_data in iteration["mcp_data"].items():
                    data_count = len(server_data) if isinstance(server_data, list) else 1
                    history_text += f"- **{server_name}**: {data_count} data points collected\n"
                    
                    if isinstance(server_data, list):
                        for item in server_data:
                            tool_name = item.get('tool', 'unknown_tool')
                            params = item.get('parameters', {})
                            
                            if tool_name == 'resources_list' and 'kind' in params or tool_name == 'resources_get' and 'kind' in params:
                                result_key = f"{tool_name}_{params['kind']}_result"
                            else:
                                result_key = f"{tool_name}_result"
                            
                            if 'result' in item:
                                result = item['result']
                                if result:
                                    formatted_data = self._format_data({"result": result})
                                    if len(formatted_data) > TRUNCATION_THRESHOLD:
                                        formatted_data = formatted_data[:TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                                    history_text += f"  - **{result_key}**:\n```\n{formatted_data}\n```\n"
                            elif 'error' in item:
                                history_text += f"  - **{result_key}_error**: {item['error']}\n"
                    elif isinstance(server_data, dict):
                        for key, value in server_data.items():
                            formatted_data = self._format_data(value)
                            if len(formatted_data) > TRUNCATION_THRESHOLD:
                                formatted_data = formatted_data[:TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                            history_text += f"  - **{key}**:\n```\n{formatted_data}\n```\n"
                    else:
                        formatted_data = self._format_data(server_data)
                        if len(formatted_data) > TRUNCATION_THRESHOLD:
                            formatted_data = formatted_data[:TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                        history_text += f"```\n{formatted_data}\n```\n"
                history_text += "\n"
            
            if "partial_analysis" in iteration:
                history_text += f"**Partial Analysis:**\n{iteration['partial_analysis']}\n\n"
            
            history_text += "---\n\n"
        
        return history_text.strip()
    
    # ============ ReAct Response Parsing (Keep Current Logic) ============
    
    def parse_react_response(self, response: str) -> Dict[str, Any]:
        """Parse structured ReAct response into components with robust error handling."""
        # Keep existing implementation from current PromptBuilder
        # (Lines 753-839 from current file)
        pass
    
    def get_react_continuation_prompt(self, context_type: str = "general") -> List[str]:
        """Get ReAct continuation prompts for when LLM provides incomplete responses."""
        # Keep existing implementation from current PromptBuilder
        # (Lines 841-858 from current file)
        pass
    
    def get_react_error_continuation(self, error_message: str) -> List[str]:
        """Get ReAct continuation prompts for error recovery."""
        # Keep existing implementation from current PromptBuilder
        # (Lines 860-873 from current file)
        pass
    
    def convert_action_to_tool_call(self, action: str, action_input: str) -> Dict[str, Any]:
        """Convert ReAct Action/Action Input to MCP tool call format."""
        # Keep existing implementation from current PromptBuilder
        # (Lines 875-939 from current file)
        pass
    
    def format_observation(self, mcp_data: Dict[str, Any]) -> str:
        """Format MCP data as observation text for ReAct."""
        # Keep existing implementation from current PromptBuilder
        # (Lines 941-963 from current file)
        pass
```

### 4. Module Initialization (`__init__.py`)
```python
from .builders import LangChainPromptBuilder

# Create shared instance
_shared_prompt_builder = LangChainPromptBuilder()

def get_prompt_builder() -> LangChainPromptBuilder:
    """Get the shared LangChainPromptBuilder instance."""
    return _shared_prompt_builder

# Backward compatibility
PromptBuilder = LangChainPromptBuilder
```

## Migration Implementation

### Step 1: Create New Module Structure
1. Create `backend/tarsy/agents/prompt_templates/` directory
2. Implement all classes above in respective files
3. Copy existing ReAct parsing methods to new builder (keep exact logic)

### Step 2: Replace Current Implementation
1. Update `backend/tarsy/agents/prompt_builder.py`:
   ```python
   # Replace entire file content with:
   from .prompt_templates import get_prompt_builder, PromptBuilder
   from .prompt_templates.components import PromptContext  # Move PromptContext
   
   # Re-export for backward compatibility
   __all__ = ['get_prompt_builder', 'PromptBuilder', 'PromptContext']
   ```

2. Move `PromptContext` dataclass to `prompt_templates/components.py`

### Step 3: Verify API Compatibility
All existing USED method signatures must remain identical:
- `build_standard_react_prompt(context: PromptContext, react_history: Optional[List[str]] = None) -> str`  
- `build_stage_analysis_react_prompt(context: PromptContext, react_history: Optional[List[str]] = None) -> str`
- `build_final_analysis_prompt(context: PromptContext) -> str`
- `build_mcp_tool_selection_prompt(context: PromptContext) -> str`
- `build_iterative_mcp_tool_selection_prompt(context: PromptContext) -> str`
- All system message methods
- All ReAct parsing methods

### Step 4: Testing Requirements
```python
def test_alert_component_formatting():
    """Test alert section handles all data types correctly."""
    component = AlertSectionTemplate()
    
    test_cases = [
        {'simple': 'value'},
        {'json_obj': {'nested': 'data'}},
        {'json_array': ['item1', 'item2']},
        {'json_string': '{"parsed": true}'},
        {'multiline': 'line1\nline2'},
        {'empty': None}
    ]
    
    for alert_data in test_cases:
        result = component.format(alert_data)
        assert "## Alert Details" in result

def test_prompt_template_composition():
    """Test LangChain templates compose correctly."""
    from langchain_core.prompts import PromptTemplate
    
    template = PromptTemplate.from_template("Hello {name}")
    result = template.format(name="World")
    assert result == "Hello World"

def test_backward_compatibility():
    """Test all existing method signatures work."""
    from tarsy.agents.prompt_builder import get_prompt_builder, PromptContext
    
    builder = get_prompt_builder()
    context = PromptContext(
        agent_name="test",
        alert_data={'test': 'data'},
        runbook_content="test runbook",
        mcp_data={},
        mcp_servers=["test"]
    )
    
    # All these should work without changes (only the methods actually used)
    react_prompt = builder.build_standard_react_prompt(context)
    stage_prompt = builder.build_stage_analysis_react_prompt(context)
    final_prompt = builder.build_final_analysis_prompt(context)
    
    assert all(isinstance(p, str) for p in [react_prompt, stage_prompt, final_prompt])
```

## Implementation Notes

1. **Keep Existing Logic**: All ReAct parsing methods, error handling, and formatting utilities should be copied exactly from current implementation
2. **Template Validation**: LangChain templates will validate variable substitution automatically
3. **Performance**: Template compilation happens once at initialization
4. **Error Handling**: LangChain provides helpful error messages for missing variables
5. **Testing**: Each component can be tested in isolation
6. **Backward Compatibility**: All public APIs remain unchanged

This design maintains exact functionality while providing clean template composition and improved maintainability.
