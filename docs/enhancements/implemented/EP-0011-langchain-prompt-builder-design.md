# LangChain PromptBuilder Design Document

**Status**: ✅ **IMPLEMENTED** - Successfully migrated to LangChain-based template system

## Architecture Overview

Replace the current `PromptBuilder` with a LangChain-based template system using a component composition pattern.

### Dependencies
```bash
uv add langchain-core
```

### File Structure
```
backend/tarsy/agents/prompts/
├── __init__.py            # Main exports and backward compatibility
├── components.py          # Reusable template components  
├── builders.py            # New LangChain PromptBuilder
├── templates.py           # LangChain template definitions
└── legacy_builder.py      # Current prompt_builder.py (during migration)
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

# Chain context formatting is handled directly via StageContext.format_previous_stages_context()
# No separate template component needed as this logic is built into the context model
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
```

### 3. Main Builder Class (`builders.py`)
```python
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from .components import (
    AlertSectionTemplate, 
    RunbookSectionTemplate
)
from .templates import *
import json

if TYPE_CHECKING:
    from tarsy.models.agent_execution_result import ChainExecutionContext

class PromptBuilder:
    """LangChain-based prompt builder with template composition."""
    
    def __init__(self):
        # Initialize component templates
        self.alert_component = AlertSectionTemplate()
        self.runbook_component = RunbookSectionTemplate()
        # Chain context formatting handled directly via StageContext.format_previous_stages_context()
    
    # ============ Main Prompt Building Methods ============
    
    def build_standard_react_prompt(self, context, react_history: Optional[List[str]] = None) -> str:
        """Build standard ReAct prompt using templates. Used by SimpleReActController."""
        # Build question components
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        chain_context = f"\n## Previous Stage Results\n\n{previous_stages_context}" if previous_stages_context != "No previous stage context available." else ""
        
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
        """Build ReAct prompt for stage-specific analysis. Used by ReactStageController."""
        # Build question components
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        chain_context = f"\n## Previous Stage Results\n\n{previous_stages_context}" if previous_stages_context != "No previous stage context available." else ""
        
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
        """Build prompt for final analysis without ReAct format. Used by ReactFinalAnalysisController."""
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
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        chain_context = f"\n## Previous Stage Results\n\n{previous_stages_context}" if previous_stages_context != "No previous stage context available." else ""
        
        return FINAL_ANALYSIS_PROMPT_TEMPLATE.format(
            stage_info=stage_info,
            context_section=context_section,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
    
    # ============ System Message Methods ============
    
    def get_enhanced_react_system_message(self, composed_instructions: str, task_focus: str = "investigation and providing recommendations") -> str:
        """Get enhanced ReAct system message using template. Used by ReAct iteration controllers."""
        return REACT_SYSTEM_TEMPLATE.format(
            composed_instructions=composed_instructions,
            task_focus=task_focus
        )
    
    def get_general_instructions(self) -> str:
        """Get general SRE instructions. Used for system prompts in Final Analysis (simplified) vs ReAct system prompts (complex)."""
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
    
    # ============ Helper Methods (Keep Current Logic) ============
    
    def _build_context_section(self, context) -> str:
        """Build the context section using template."""
        server_list = ", ".join(context.mcp_servers)
        return CONTEXT_SECTION_TEMPLATE.format(
            agent_name=context.agent_name,
            server_list=server_list
        )
    
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

    # ============ ReAct Response Parsing (Keep Current Logic) ============
    
    def parse_react_response(self, response: str) -> Dict[str, Any]:
        """Parse structured ReAct response into components with robust error handling."""
        # Keep existing implementation from current PromptBuilder
        # Copy exact logic from lines 484-571 in current prompt_builder.py
        pass
    
    def get_react_continuation_prompt(self, context_type: str = "general") -> List[str]:
        """Get ReAct continuation prompts for when LLM provides incomplete responses."""
        # Keep existing implementation from current PromptBuilder
        # Copy exact logic from lines 572-590 in current prompt_builder.py
        pass
    
    def get_react_error_continuation(self, error_message: str) -> List[str]:
        """Get ReAct continuation prompts for error recovery."""
        # Keep existing implementation from current PromptBuilder
        # Copy exact logic from lines 591-605 in current prompt_builder.py
        pass
    
    def convert_action_to_tool_call(self, action: str, action_input: str) -> Dict[str, Any]:
        """Convert ReAct Action/Action Input to MCP tool call format."""
        # Keep existing implementation from current PromptBuilder
        # Copy exact logic from lines 606-671 in current prompt_builder.py
        pass
    
    def format_observation(self, mcp_data: Dict[str, Any]) -> str:
        """Format MCP data as observation text for ReAct."""
        # Keep existing implementation from current PromptBuilder
        # Copy exact logic from lines 672-695 in current prompt_builder.py
        pass
```

### 4. Module Initialization (`__init__.py`)
```python
from .builders import PromptBuilder

# Create shared instance
_shared_prompt_builder = PromptBuilder()

def get_prompt_builder() -> PromptBuilder:
    """Get the shared PromptBuilder instance."""
    return _shared_prompt_builder

# Re-export for backward compatibility
__all__ = ['PromptBuilder', 'get_prompt_builder']
```

## Migration Implementation

### Step 1: Create New Package Structure
1. Create `backend/tarsy/agents/prompts/` directory
2. Move existing `prompt_builder.py` to `prompts/legacy_builder.py`  
3. Implement new LangChain classes in respective files
4. Copy existing ReAct parsing methods to new builder (keep exact logic)

### Step 2: Create Backward Compatibility Layer
1. Create new `backend/tarsy/agents/prompt_builder.py` as re-export:
   ```python
   # Backward compatibility re-exports
   from .prompts import get_prompt_builder, PromptBuilder, PromptContext
   
   __all__ = ['get_prompt_builder', 'PromptBuilder', 'PromptContext']
   ```

2. Move `PromptContext` dataclass to `prompts/components.py`

### Step 3: Implement LangChain Components
1. **`prompts/components.py`** - Template components and PromptContext
2. **`prompts/templates.py`** - LangChain template definitions
3. **`prompts/builders.py`** - New LangChain PromptBuilder
4. **`prompts/__init__.py`** - Package exports and shared instance

### Step 4: Verify API Compatibility
All existing USED method signatures must remain identical:
- `build_standard_react_prompt(context: PromptContext, react_history: Optional[List[str]] = None) -> str`  
- `build_stage_analysis_react_prompt(context: PromptContext, react_history: Optional[List[str]] = None) -> str`
- `build_final_analysis_prompt(context: PromptContext) -> str`
- `get_enhanced_react_system_message(composed_instructions: str, task_focus: str = "investigation and providing recommendations") -> str`
- `get_general_instructions() -> str`
- All ReAct parsing methods

### Step 5: Fix Type Safety Issues
Update all iteration controllers to have proper type annotations:

1. **Update `react_iteration_controller.py`:**
   ```python
   from typing import TYPE_CHECKING
   
   if TYPE_CHECKING:
       from tarsy.integrations.llm.client import LLMClient
       from tarsy.agents.prompt_builder import PromptBuilder
   
   class SimpleReActController(IterationController):
       def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
           """Initialize with proper type annotations."""
           self.llm_client = llm_client
           self.prompt_builder = prompt_builder
   ```

2. **Update `react_stage_controller.py`:**
   ```python
   from typing import TYPE_CHECKING
   
   if TYPE_CHECKING:
       from tarsy.integrations.llm.client import LLMClient
       from tarsy.agents.prompt_builder import PromptBuilder
   
   class ReactStageController(IterationController):
       def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
           """Initialize with proper type annotations."""
           self.llm_client = llm_client
           self.prompt_builder = prompt_builder
   ```

3. **Update `react_final_analysis_controller.py`:**
   ```python
   from typing import TYPE_CHECKING
   
   if TYPE_CHECKING:
       from tarsy.integrations.llm.client import LLMClient
       from tarsy.agents.prompt_builder import PromptBuilder
   
   class ReactFinalAnalysisController(IterationController):
       def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
           """Initialize with proper type annotations."""
           self.llm_client = llm_client
           self.prompt_builder = prompt_builder
   ```

**Benefits of Type Safety:**
- IDE support with proper autocomplete and error checking
- Runtime type validation with mypy
- Clear contracts between components
- Future-proof when migrating to new PromptBuilder

### Step 6: Testing Requirements
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
        mcp_servers=["test"]
    )
    
    # Only test methods that actually exist
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