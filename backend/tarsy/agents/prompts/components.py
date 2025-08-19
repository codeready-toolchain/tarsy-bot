"""
Template components for prompt building using LangChain.

This module contains reusable template components that can be composed
to build complex prompts with proper formatting and type handling.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from langchain_core.prompts import PromptTemplate

if TYPE_CHECKING:
    from tarsy.models.agent_execution_result import ChainExecutionContext


@dataclass
class PromptContext:
    """Context data needed for prompt building."""
    agent_name: str
    alert_data: Dict[str, Any]
    runbook_content: str
    mcp_servers: List[str]
    available_tools: Optional[Dict] = None
    # Stage context for chain processing
    stage_name: Optional[str] = None
    is_final_stage: bool = False
    previous_stages: Optional[List[str]] = None
    chain_context: Optional['ChainExecutionContext'] = None


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
        if isinstance(value, (dict, list)):
            return f"\n```json\n{json.dumps(value, indent=2, ensure_ascii=False)}\n```"
        elif isinstance(value, str):
            if value.startswith(("{", "[")):
                try:
                    parsed = json.loads(value)
                    return f"\n```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```"
                except json.JSONDecodeError:
                    return value
            elif '\n' in value:
                return f"\n```\n{value}\n```"
            else:
                return value
        elif value is None:
            return "N/A"
        else:
            return str(value)


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
