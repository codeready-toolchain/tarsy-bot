# Expected conversation structures for the data collection stage tool summarization interaction, when the system info is too large to fit in the conversation
EXPECTED_DATA_COLLECTION_SUMMARIZATION_CONVERSATION = {
    "messages": [
        {
            "role": "system", 
            "content": """You are an expert at summarizing technical output from system administration and monitoring tools for ongoing incident investigation.

Your specific task is to summarize output from **test-data-server.collect_system_info** in a way that:

1. **Preserves Critical Information**: Keep all details essential for troubleshooting and investigation
2. **Maintains Investigation Context**: Focus on information relevant to what the investigator was looking for
3. **Reduces Verbosity**: Remove redundant details while preserving technical accuracy  
4. **Highlights Key Findings**: Emphasize errors, warnings, unusual patterns, and actionable insights
5. **Stays Concise**: Keep summary under 50 tokens while preserving meaning

## Summarization Guidelines:

- **Always Preserve**: Error messages, warnings, status indicators, resource metrics, timestamps
- **Intelligently Summarize**: Large lists by showing patterns, counts, and notable exceptions
- **Focus On**: Non-default configurations, problematic settings, resource utilization issues
- **Maintain**: Technical accuracy and context about what the data represents
- **Format**: Clean, structured text suitable for continued technical investigation

Your summary will be inserted as an observation in the ongoing investigation conversation."""
        },
        {
            "role": "user",
            "content": """Below is the ongoing investigation conversation that provides context for what the investigator has been looking for and thinking about:

## Investigation Context:
=== CONVERSATION START ===
SYSTEM: ## General SRE Agent Instructions

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
Focus on root cause analysis and sustainable solutions.

## Kubernetes Server Instructions

For Kubernetes operations:
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- Use kubectl explain for resource schema information
- Check resource quotas before creating new resources

## Custom Server Instructions

Simple data collection server for testing - provides system information gathering tools

## Agent-Specific Instructions

You are a Kubernetes data collection specialist. Your role is to gather comprehensive 
information about problematic resources using available kubectl tools.

Focus on:
- Namespace status and finalizers
- Pod states and termination details  
- Events showing errors and warnings
- Resource dependencies that might block cleanup

Be thorough but efficient. Collect all relevant data before stopping.

USER: Answer the following question using the available tools.

Available tools:

1. **kubernetes-server.kubectl_get**: Get Kubernetes resources
    **Parameters**:
    - resource (optional, string): No description
    - namespace (optional, string): No description
    - name (optional, string): No description

2. **kubernetes-server.kubectl_describe**: Describe Kubernetes resources
    **Parameters**:
    - resource (optional, string): No description
    - namespace (optional, string): No description
    - name (optional, string): No description

3. **test-data-server.collect_system_info**: Collect basic system information like CPU, memory, and disk usage
    **Parameters**:
    - detailed (optional, boolean): Whether to return detailed system info

Question: Investigate this test-kubernetes alert and provide stage-specific analysis.

## Alert Details

### Alert Metadata
**Alert Type:** test-kubernetes
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "namespace": "test-namespace",
  "description": "Namespace stuck in Terminating state",
  "cluster": "test-cluster",
  "labels": {
    "env": "test",
    "team": "platform"
  },
  "annotations": {
    "finalizers": "kubernetes.io/pv-protection"
  }
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Mock Runbook
Test runbook content
<!-- RUNBOOK END -->
```

## Previous Stage Data
No previous stage data is available for this alert. This is the first stage of analysis.

## Your Task: DATA-COLLECTION STAGE
Use available tools to:
1. Collect additional data relevant to this stage
2. Analyze findings in the context of this specific stage
3. Provide stage-specific insights and recommendations

Your Final Answer should include both the data collected and your stage-specific analysis.

Begin!

ASSISTANT: Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}

USER: Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}

ASSISTANT: Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}

USER: Observation: kubernetes-server.kubectl_describe error: Tool execution failed: Failed to call tool kubectl_describe on kubernetes-server after 2 attempts: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message="tool 'kubectl_describe' not found: tool not found", data=None)

ASSISTANT: Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}
=== CONVERSATION END ===

## Tool Result to Summarize:
The investigator just executed `test-data-server.collect_system_info` and got the following output:

=== TOOL OUTPUT START ===
{'result': 'Long System Information Report - more than 100 tokens\\n8wHXXQkrjqtaYwXb3KdmeOapEKU27hMiaYvzT25SI4MexrI2SC9gFLsKie0eDxH5WEVV7TvDCWjOrD2egFSykp2eRP2u9jVwUqzgOVULB6WAnTKol7vmIii9F7gCWoKMXnJsh12fppgIWJAbFw5vYuv7JIQMargw3vxFZO699z3t0hiYPtcLyeSXyyIf0lIxl8lOmKLsYA4TBZiSwZ6V5NV1cZ2VQeMxDOLN4F6kjTaqCtTc7zGCYzvHlv9BaCVB4SXo26yfg3r2G7sCRjexj0EvKGxnYecJiJoEtqD01pCCBrlQC8esGoG15NaMlFCWIsbdJmADZOR0WUYOcOhNk0WOtASqzHJBIfnGVYYxGMq0A5DkPGbUe4UXYPNEnD0xZ7YcEYGKAmdYmx2F2BgMi2NYXcelZ1Ym1Ukx2zGZoiKVmBdutnWr2ManM0PnChDLj0SyIZGdmhZhOn5R9uB3HpbCXsKzw4gUYiU9EvwW2m22pe6zKTSCpyhI4rVG5fFwrehWEbuB8nTbI3eawqQQevCbal42ko0GBG1sjE2GIDn7jmwJEBImlxRkuHoyWvMqfLDn9RbGXzhtnlO7sKZEb9He'}
=== TOOL OUTPUT END ===

## Your Task:
Based on the investigation context above, provide a concise summary of the tool result that:
- Preserves information most relevant to what the investigator was looking for
- Removes verbose or redundant details that don't impact the investigation
- Maintains technical accuracy and actionable insights
- Fits naturally as the next "Observation:" in the investigation conversation

CRITICAL INSTRUCTION: You MUST return ONLY plain text. DO NOT include "Final Answer:", "Thought:", "Action:", or any other formatting. Just the summary text that will be inserted as an observation in the conversation."""
        },
        {
            "role": "assistant",
            "content": """Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK."""
        }
    ]
}

"""
Expected stage interactions for the complete alert processing flow

Format:
<stage_name>: {
    "llm_count": <number of LLM interactions>,
    "mcp_count": <number of MCP interactions>,
    "interactions": [
        {"type": "mcp", "position": <position_among_mcp_interactions>, "communication_type": <tool_list or tool_call>, "success": <success>, "server_name": <server_name>},
        {"type": "llm", "position": <position_among_llm_interactions>, "success": <success>, "conversation_index": <the number of messages from the expected conversation that should be included in the actual conversation, starting from 0>, "input_tokens": n, "output_tokens": n, "total_tokens": n},
    ]
}
"""
# Expected stages for the complete alert processing flow
EXPECTED_STAGES = {
    'data-collection': {
        'llm_count': 6,  # 5 regular interactions plus 1 tool result summarization interaction  
        'mcp_count': 6,  # Tool discovery calls + tool execution calls are all tracked as MCP interactions
        'interactions': [
            # MCP 1 - Tool list discovery for kubernetes-server (first interaction)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # MCP 2 - Tool list discovery for test-data-server (returns 1 tool: collect_system_info)
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Initial ReAct iteration
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 245, 'output_tokens': 85, 'total_tokens': 330},
            # MCP 3 - Successful kubectl_get attempt
            {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Second ReAct iteration
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245},
            # MCP 4 - Failed kubectl_describe attempt (testing error handling)
            {'type': 'mcp', 'position': 4, 'communication_type': 'tool_call', 'success': False, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server', 'error_message': "Failed to call tool kubectl_describe on kubernetes-server after 2 attempts: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message=\"tool 'kubectl_describe' not found: tool not found\", data=None)"},
            # LLM 3 - Third ReAct iteration
            {'type': 'llm', 'position': 3, 'success': True, 'conversation_index': 7, 'input_tokens': 220, 'output_tokens': 75, 'total_tokens': 295},
            # LLM 4 - Summarization of large system info result (separate LLM call, not in conversation)
            # The summarization interaction happens within the collect_system_info MCP call interaction, so it's recorded before the MCP interaction
            {'type': 'llm', 'position': 4, 'success': True, 'conversation': EXPECTED_DATA_COLLECTION_SUMMARIZATION_CONVERSATION, 'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150},
            # MCP 5 - Successful collect_system_info call (will trigger summarization)
            {'type': 'mcp', 'position': 5, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'collect_system_info', 'server_name': 'test-data-server'},
            # LLM 5 - Fourth ReAct iteration (kubectl events call) - continues after system info
            {'type': 'llm', 'position': 5, 'success': True, 'conversation_index': 9, 'input_tokens': 200, 'output_tokens': 60, 'total_tokens': 260},
            # MCP 6 - Successful kubectl_get events call
            {'type': 'mcp', 'position': 6, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 6 - Final completion with events observation
            {'type': 'llm', 'position': 6, 'success': True, 'conversation_index': 11, 'input_tokens': 315, 'output_tokens': 125, 'total_tokens': 440}
        ]
    },
    'verification': {
        'llm_count': 2,
        'mcp_count': 2,  # Tool discovery calls + tool execution calls are all tracked as MCP interactions
        'interactions': [
            # MCP 1 - Tool list discovery (first interaction)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # LLM 1 - Initial ReAct iteration
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 190, 'output_tokens': 70, 'total_tokens': 260},
            # MCP 2 - Successful kubectl_get attempt
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 280, 'output_tokens': 110, 'total_tokens': 390}
        ]
    },
    'analysis': {
        'llm_count': 1,
        'mcp_count': 0,
        'interactions': [
            # LLM 1 - Final analysis (no tool discovery)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 420, 'output_tokens': 180, 'total_tokens': 600}
        ]
    }
}

"""
Expected conversation structures for E2E tests.

This module contains the expected LLM conversation message structures
for different stages in EP-0014 format. Each stage defines the exact
sequence of messages (system, user, assistant) that should appear
in the progressive conversation structure.

Format:
<stage_name>: {
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."},
        # ... more messages
    ]
}
"""

# Expected conversation structures for multi-stage chains
EXPECTED_DATA_COLLECTION_CONVERSATION = {
    "messages": [
        {
            "role": "system", 
            "content": """## General SRE Agent Instructions

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
Focus on root cause analysis and sustainable solutions.

## Kubernetes Server Instructions

For Kubernetes operations:
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- Use kubectl explain for resource schema information
- Check resource quotas before creating new resources

## Custom Server Instructions

Simple data collection server for testing - provides system information gathering tools

## Agent-Specific Instructions

You are a Kubernetes data collection specialist. Your role is to gather comprehensive 
information about problematic resources using available kubectl tools.

Focus on:
- Namespace status and finalizers
- Pod states and termination details  
- Events showing errors and warnings
- Resource dependencies that might block cleanup

Be thorough but efficient. Collect all relevant data before stopping.

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
❌ Observation: kubernetes-server.resources_get: {"result": "..."} 
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
❌ WRONG: "Thought
The user wants me to investigate..."
❌ WRONG: "Action
kubernetes-server.resources_get"
✅ CORRECT: "Thought:
The user wants me to investigate..."
✅ CORRECT: "Action:
kubernetes-server.resources_get"

THE #1 MISTAKE: Writing fake observations and continuing the conversation after Action Input

Focus on collecting additional data and providing stage-specific analysis for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Answer the following question using the available tools.

Available tools:

1. **kubernetes-server.kubectl_get**: Get Kubernetes resources
    **Parameters**:
    - resource (optional, string): No description
    - namespace (optional, string): No description
    - name (optional, string): No description

2. **kubernetes-server.kubectl_describe**: Describe Kubernetes resources
    **Parameters**:
    - resource (optional, string): No description
    - namespace (optional, string): No description
    - name (optional, string): No description

3. **test-data-server.collect_system_info**: Collect basic system information like CPU, memory, and disk usage
    **Parameters**:
    - detailed (optional, boolean): Whether to return detailed system info

Question: Investigate this test-kubernetes alert and provide stage-specific analysis.

## Alert Details

### Alert Metadata
**Alert Type:** test-kubernetes
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "namespace": "test-namespace",
  "description": "Namespace stuck in Terminating state",
  "cluster": "test-cluster",
  "labels": {
    "env": "test",
    "team": "platform"
  },
  "annotations": {
    "finalizers": "kubernetes.io/pv-protection"
  }
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Mock Runbook
Test runbook content
<!-- RUNBOOK END -->
```

## Previous Stage Data
No previous stage data is available for this alert. This is the first stage of analysis.

## Your Task: DATA-COLLECTION STAGE
Use available tools to:
1. Collect additional data relevant to this stage
2. Analyze findings in the context of this specific stage
3. Provide stage-specific insights and recommendations

Your Final Answer should include both the data collected and your stage-specific analysis.

Begin!"""
        },
        # 1st LLM interaction ends here with assistant response
        {
            "role": "assistant",
            "content": """Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
        },
        # 2nd LLM interaction adds observation and gets next assistant response
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}"""
        },
        {
            "role": "assistant", 
            "content": """Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}"""
        },
        # 3rd LLM interaction adds observation and gets next assistant response
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_describe error: Tool execution failed: Failed to call tool kubectl_describe on kubernetes-server after 2 attempts: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message="tool 'kubectl_describe' not found: tool not found", data=None)"""
        },
        {
            "role": "assistant",
            "content": """Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}"""
        },
        # 4th LLM interaction - Gets summarized system info and continues with HTTP check
        {
            "role": "user",
            "content": """Observation: test-data-server.collect_system_info: {
  "result": "Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK."
}"""
        },
        {
            "role": "assistant",
            "content": """Thought: Let me gather more information about the current state.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "namespace": "test-namespace"}"""
        },
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "Mock kubectl get events response"
}"""
        },
        {
            "role": "assistant", 
            "content": """Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion."""
        }
    ]
}

EXPECTED_VERIFICATION_CONVERSATION = {
    "messages": [
        {
            "role": "system", 
            "content": """## General SRE Agent Instructions

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
Focus on root cause analysis and sustainable solutions.

## Kubernetes Server Instructions

For Kubernetes operations:
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- Use kubectl explain for resource schema information
- Check resource quotas before creating new resources

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
❌ Observation: kubernetes-server.resources_get: {"result": "..."} 
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
❌ WRONG: "Thought
The user wants me to investigate..."
❌ WRONG: "Action
kubernetes-server.resources_get"
✅ CORRECT: "Thought:
The user wants me to investigate..."
✅ CORRECT: "Action:
kubernetes-server.resources_get"

THE #1 MISTAKE: Writing fake observations and continuing the conversation after Action Input

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Answer the following question using the available tools.

Available tools:

1. **kubernetes-server.kubectl_get**: Get Kubernetes resources
    **Parameters**:
    - resource (optional, string): No description
    - namespace (optional, string): No description
    - name (optional, string): No description

2. **kubernetes-server.kubectl_describe**: Describe Kubernetes resources
    **Parameters**:
    - resource (optional, string): No description
    - namespace (optional, string): No description
    - name (optional, string): No description

Question: Analyze this test-kubernetes alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-kubernetes
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "namespace": "test-namespace",
  "description": "Namespace stuck in Terminating state",
  "cluster": "test-cluster",
  "labels": {
    "env": "test",
    "team": "platform"
  },
  "annotations": {
    "finalizers": "kubernetes.io/pv-protection"
  }
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Mock Runbook
Test runbook content
<!-- RUNBOOK END -->
```

## Previous Stage Data
### Results from 'data-collection' stage:

#### Analysis Result

<!-- Analysis Result START -->
Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}
Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}
Observation: kubernetes-server.kubectl_describe error: Tool execution failed: Failed to call tool kubectl_describe on kubernetes-server after 2 attempts: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message="tool 'kubectl_describe' not found: tool not found", data=None)
Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}
Observation: test-data-server.collect_system_info: {
  "result": "Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK."
}
Thought: Let me gather more information about the current state.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "namespace": "test-namespace"}
Observation: kubernetes-server.kubectl_get: {
  "result": "Mock kubectl get events response"
}
Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion.
<!-- Analysis Result END -->


## Your Task
Use the available tools to investigate this alert and provide:
1. Root cause analysis
2. Current system state assessment  
3. Specific remediation steps for human operators
4. Prevention recommendations

Be thorough in your investigation before providing the final answer.

Begin!"""
        },
        # 1st LLM interaction ends here with assistant response
        {
            "role": "assistant",
            "content": """Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
        },
        # 2nd LLM interaction adds observation and gets final response  
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}"""
        },
        {
            "role": "assistant",
            "content": """Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion."""
        }
    ]
}

EXPECTED_ANALYSIS_CONVERSATION = {
    "messages": [
        {
            "role": "system", 
            "content": """## General SRE Agent Instructions

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
Focus on root cause analysis and sustainable solutions.

## Agent-Specific Instructions
You are a Senior Site Reliability Engineer specializing in Kubernetes troubleshooting.
Analyze the collected data from previous stages to identify root causes.

Your analysis should:
- Synthesize information from all data collection activities
- Identify the specific root cause of the problem
- Assess the impact and urgency level
- Provide confidence levels for your conclusions

Be precise and actionable in your analysis."""
        },
        {
            "role": "user",
            "content": """# Final Analysis Task


**Stage:** analysis (Final Analysis Stage)


# SRE Alert Analysis Request

You are an expert Site Reliability Engineer (SRE) analyzing a system alert using the ConfigurableAgent.
This agent specializes in kubernetes-server operations and has access to domain-specific tools and knowledge.

Your task is to provide a comprehensive analysis of the incident based on:
1. The alert information
2. The associated runbook
3. Real-time system data from MCP servers

Please provide detailed, actionable insights about what's happening and potential next steps.

## Alert Details

### Alert Metadata
**Alert Type:** test-kubernetes
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "namespace": "test-namespace",
  "description": "Namespace stuck in Terminating state",
  "cluster": "test-cluster",
  "labels": {
    "env": "test",
    "team": "platform"
  },
  "annotations": {
    "finalizers": "kubernetes.io/pv-protection"
  }
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Mock Runbook
Test runbook content
<!-- RUNBOOK END -->
```

## Previous Stage Data
### Results from 'data-collection' stage:

#### Analysis Result

<!-- Analysis Result START -->
Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}
Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}
Observation: kubernetes-server.kubectl_describe error: Tool execution failed: Failed to call tool kubectl_describe on kubernetes-server after 2 attempts: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message="tool 'kubectl_describe' not found: tool not found", data=None)
Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}
Observation: test-data-server.collect_system_info: {
  "result": "Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK."
}
Thought: Let me gather more information about the current state.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "namespace": "test-namespace"}
Observation: kubernetes-server.kubectl_get: {
  "result": "Mock kubectl get events response"
}
Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion.
<!-- Analysis Result END -->

### Results from 'verification' stage:

#### Analysis Result

<!-- Analysis Result START -->
Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}
Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}
Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.
<!-- Analysis Result END -->


## Instructions
Provide comprehensive final analysis based on ALL collected data:
1. Root cause analysis
2. Impact assessment  
3. Recommended actions
4. Prevention strategies

Do NOT call any tools - use only the provided data."""
        },
        {
            "role": "assistant",
            "content": "Based on previous stages, the namespace is stuck due to finalizers."
        }
    ]
}
