# ruff: noqa: E501  # Long instructional templates intentionally exceed 88 characters
"""
LangChain template definitions for prompt building.

This module contains all the LangChain PromptTemplate definitions used
for building various types of prompts in the system.
"""

from langchain_core.prompts import PromptTemplate

# ReAct formatting instructions constant
REACT_FORMATTING_INSTRUCTIONS = """You are an SRE agent using the ReAct framework to analyze Kubernetes incidents. Reason step by step, act with tools, observe results, and repeat until you identify root cause and resolution steps.

REQUIRED FORMAT:

Question: [the incident question]
Thought: [your step-by-step reasoning]
Action: [tool name from available tools]
Action Input: [parameters as key: value pairs]

⚠️ STOP immediately after Action Input. The system provides Observations.

Continue the cycle. Conclude when you have sufficient information:

Thought: [final reasoning]
Final Answer: [complete structured response]

CRITICAL RULES:
1. Always use colons after headers: "Thought:", "Action:", "Action Input:"
2. Start each section on a NEW LINE (never continue on same line as previous text)
3. Stop after Action Input—never generate fake Observations
4. Parameters: one per line for multiple values, or inline for single value
5. Conclude when you have actionable insights (perfect information not required)

PARAMETER FORMATS:

Multiple parameters:
Action Input: apiVersion: v1
kind: Namespace
name: superman-dev

Single parameter:
Action Input: namespace: default

EXAMPLE CYCLE:

Question: Why is namespace 'superman-dev' stuck in terminating state?

Thought: I need to check the namespace status first to identify any blocking resources or finalizers.

Action: kubernetes-server.resources_get
Action Input: apiVersion: v1
kind: Namespace
name: superman-dev

[System provides: Observation: {"status": {"phase": "Terminating", "finalizers": ["kubernetes"]}}]

Thought: A finalizer is blocking deletion. I should check for any remaining resources in the namespace.

Action: kubernetes-server.resources_list
Action Input: apiVersion: v1
kind: Pod
namespace: superman-dev

[System provides: Observation: No pods found]

Thought: No pods remain, but the finalizer persists. This is an orphaned finalizer that needs manual removal.

Final Answer: 
**Root Cause:** Orphaned 'kubernetes' finalizer blocking namespace deletion after all resources were cleaned up.

**Resolution Steps:**
1. Remove the finalizer: `kubectl patch namespace superman-dev -p '{"spec":{"finalizers":null}}' --type=merge`
2. Verify deletion: `kubectl get namespace superman-dev`
3. If still stuck, check for remaining resources: `kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get -n superman-dev`

**Preventive Measures:** Ensure cleanup scripts remove finalizers when deleting namespaces programmatically."""

# Updated ReAct System Message Template  
REACT_SYSTEM_TEMPLATE = PromptTemplate.from_template("""{composed_instructions}

{react_formatting_instructions}

Focus on {task_focus} for human operators to execute.""")


# Standard ReAct Prompt Template
STANDARD_REACT_PROMPT_TEMPLATE = PromptTemplate.from_template("""Answer the following question using the available tools.

Available tools:

{available_actions}

Question: {question}

{history_text}Begin!""")


# Synthesis Prompt Template (no tools section)
# Used for synthesis stages which don't use tools - just analyzes and combines results
# Simple instruction with context (alert + runbook + previous stages)
SYNTHESIS_PROMPT_TEMPLATE = PromptTemplate.from_template("""Synthesize the investigation results and provide recommendations.

{context}

{history_text}Begin!""")


# Analysis Question Template
ANALYSIS_QUESTION_TEMPLATE = PromptTemplate.from_template("""Analyze this {alert_type} alert and provide actionable recommendations.

{alert_section}

{runbook_section}

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


# MCP Result Summarization Templates
MCP_SUMMARIZATION_SYSTEM_TEMPLATE = PromptTemplate.from_template("""You are an expert at summarizing technical output from system administration and monitoring tools for ongoing incident investigation.

Your specific task is to summarize output from **{server_name}.{tool_name}** in a way that:

1. **Preserves Critical Information**: Keep all details essential for troubleshooting and investigation
2. **Maintains Investigation Context**: Focus on information relevant to what the investigator was looking for
3. **Reduces Verbosity**: Remove redundant details while preserving technical accuracy  
4. **Highlights Key Findings**: Emphasize errors, warnings, unusual patterns, and actionable insights
5. **Stays Concise**: Keep summary under {max_summary_tokens} tokens while preserving meaning

## Summarization Guidelines:

- **Always Preserve**: Error messages, warnings, status indicators, resource metrics, timestamps
- **Intelligently Summarize**: Large lists by showing patterns, counts, and notable exceptions
- **Focus On**: Non-default configurations, problematic settings, resource utilization issues
- **Maintain**: Technical accuracy and context about what the data represents
- **Format**: Clean, structured text suitable for continued technical investigation

Your summary will be inserted as an observation in the ongoing investigation conversation.""")

MCP_SUMMARIZATION_USER_TEMPLATE = PromptTemplate.from_template("""Below is the ongoing investigation conversation that provides context for what the investigator has been looking for and thinking about:

## Investigation Context:
=== CONVERSATION START ===
{conversation_context}
=== CONVERSATION END ===

## Tool Result to Summarize:
The investigator just executed `{server_name}.{tool_name}` and got the following output:

=== TOOL OUTPUT START ===
{result_text}
=== TOOL OUTPUT END ===

## Your Task:
Based on the investigation context above, provide a concise summary of the tool result that:
- Preserves information most relevant to what the investigator was looking for
- Removes verbose or redundant details that don't impact the investigation
- Maintains technical accuracy and actionable insights
- Fits naturally as the next "Observation:" in the investigation conversation

CRITICAL INSTRUCTION: You MUST return ONLY plain text. DO NOT include "Final Answer:", "Thought:", "Action:", or any other formatting. Just the summary text that will be inserted as an observation in the conversation.""")


# ==============================================================================
# NATIVE THINKING TEMPLATES (Gemini-specific)
# ==============================================================================
# These templates are used with the NATIVE_THINKING iteration strategy.
# They don't include ReAct format instructions since Gemini uses native
# function calling and internal reasoning.

# Native Thinking System Message Template
NATIVE_THINKING_SYSTEM_TEMPLATE = PromptTemplate.from_template("""{composed_instructions}

You are an SRE agent analyzing incidents. Use the available tools to investigate and provide actionable recommendations.

When you have gathered sufficient information, provide your final analysis with:
1. Root cause analysis
2. Current system state assessment
3. Specific remediation steps for human operators
4. Prevention recommendations

Focus on {task_focus} for human operators to execute.""")


# Native Thinking Analysis Question Template (simplified, no ReAct format)
NATIVE_THINKING_ANALYSIS_TEMPLATE = PromptTemplate.from_template("""Analyze this {alert_type} alert and provide actionable recommendations.

{alert_section}

{runbook_section}

{chain_context}

## Your Task
Investigate this alert using the available tools and provide:
1. Root cause analysis based on your investigation
2. Current system state assessment from tool observations
3. Specific remediation steps for human operators
4. Prevention recommendations

Use tools as needed to gather information. When you have sufficient data, provide your complete analysis.""")
