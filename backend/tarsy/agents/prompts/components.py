"""
Template components for prompt building using LangChain.

This module contains reusable template components that can be composed
to build complex prompts with proper formatting and type handling.
"""

import json

from langchain_core.prompts import PromptTemplate

from tarsy.models.alert import ProcessingAlert


class AlertSectionTemplate:
    """
    Formats alert data with separate metadata and client data sections.
    
    Shows:
    1. Alert Metadata: Our normalized fields (alert_type, timestamp)
    2. Alert Data: Client's pristine data (preserved exactly as received)
    """
    
    template = PromptTemplate.from_template("""## Alert Details

{formatted_content}""")
    
    def format(self, processing_alert: ProcessingAlert) -> str:
        """
        Format ProcessingAlert into sections for LLM prompts.
        
        Args:
            processing_alert: ProcessingAlert with metadata and client data
            
        Returns:
            Formatted string with metadata and data sections
        """
        sections = []
        
        # Section 1: Alert Metadata
        sections.append("### Alert Metadata")
        sections.append(f"**Alert Type:** {processing_alert.alert_type}")
        sections.append(f"**Timestamp:** {processing_alert.timestamp}")
        
        # Section 2: Alert Data (Client's pristine data)
        sections.append("")
        sections.append("### Alert Data")
        if processing_alert.alert_data:
            sections.append("```json")
            sections.append(json.dumps(processing_alert.alert_data, indent=2, ensure_ascii=False))
            sections.append("```")
        else:
            sections.append("No additional alert data provided.")
        
        formatted_content = "\n".join(sections)
        return self.template.format(formatted_content=formatted_content)

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
