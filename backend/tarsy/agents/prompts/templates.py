# ruff: noqa: E501  # Long instructional templates intentionally exceed 88 characters
"""
LangChain template definitions for prompt building.

This module contains all the LangChain PromptTemplate definitions used
for building various types of prompts in the system.
"""

from langchain_core.prompts import PromptTemplate


# ReAct formatting instructions constant
REACT_FORMATTING_INSTRUCTIONS = """
🚨 WARNING: NEVER GENERATE FAKE OBSERVATIONS! 🚨
After writing "Action Input:", you MUST stop immediately. The system will provide the "Observation:" for you.
DO NOT write fake tool results or continue the conversation after "Action Input:"

🔥 CRITICAL COLON FORMATTING RULE 🔥
EVERY ReAct section header MUST END WITH A COLON (:)

✅ CORRECT: "Thought:" (with colon)
❌ INCORRECT: "Thought" (missing colon)

You MUST write:
- "Thought:" (NOT "Thought")  
- "Action:" (NOT "Action")
- "Action Input:" (NOT "Action Input")

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
🚨 ❌ MISSING COLONS: Writing "Thought" instead of "Thought:" - THIS IS THE #1 FORMATTING ERROR
❌ Action Input with ```yaml or code blocks  
❌ Running sections together on the same line without proper newlines
❌ Providing analysis in non-ReAct format (you MUST use "Final Answer:" to conclude)
❌ Abandoning ReAct format and providing direct structured responses

🔥 COLON EXAMPLES - MEMORIZE THESE:
❌ WRONG: "Thought\nThe user wants me to investigate..."
❌ WRONG: "Action\nkubernetes-server.resources_get"
✅ CORRECT: "Thought:\nThe user wants me to investigate..."
✅ CORRECT: "Action:\nkubernetes-server.resources_get"

THE #1 MISTAKE: Writing fake observations and continuing the conversation after Action Input"""

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

The summary will be used as an observation in the ongoing ReAct investigation process.""")
