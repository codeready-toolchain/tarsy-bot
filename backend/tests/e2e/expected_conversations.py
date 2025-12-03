from pathlib import Path

# Helper function to load chat message templates from external files
def load_chat_message_template(filename: str) -> str:
    """Load a chat message template from the chat_message_templates directory."""
    template_dir = Path(__file__).parent / "chat_message_templates"
    template_path = template_dir / filename
    with open(template_path, "r") as f:
        # Strip trailing newline to match actual LLM conversation format
        return f.read().rstrip('\n')


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
- **IMPORTANT: In multi-cluster environments** (when the 'configuration_contexts_list' tool is available):
  * ALWAYS start by calling 'configuration_contexts_list' to see all available contexts and their server URLs
  * Use this information to determine which context to target before performing any operations
  * This prevents working on the wrong cluster and helps you understand the environment
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- If you get "server could not find the requested resource" error, check if you're using the namespace parameter correctly:
  * Cluster-scoped resources (Namespace, Node, ClusterRole, PersistentVolume) should NOT have a namespace parameter
  * Namespace-scoped resources (Pod, Deployment, Service, ConfigMap) REQUIRE a namespace parameter

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
  "contact": "__MASKED_EMAIL__",
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

USER: Observation: kubernetes-server.kubectl_describe error: Tool execution failed: Failed to call tool kubectl_describe on kubernetes-server: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message="tool 'kubectl_describe' not found: tool not found", data=None)

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
            # LLM 1 - Initial ReAct iteration (investigation type)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 245, 'output_tokens': 85, 'total_tokens': 330, 'interaction_type': 'investigation'},
            # MCP 3 - Successful kubectl_get attempt
            {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Second ReAct iteration (investigation type)
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245, 'interaction_type': 'investigation'},
            # MCP 4 - Failed kubectl_describe attempt (testing error handling)
            {'type': 'mcp', 'position': 4, 'communication_type': 'tool_call', 'success': False, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server', 'error_message': "Failed to call tool kubectl_describe on kubernetes-server: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message=\"tool 'kubectl_describe' not found: tool not found\", data=None)"},
            # LLM 3 - Third ReAct iteration (investigation type)
            {'type': 'llm', 'position': 3, 'success': True, 'conversation_index': 7, 'input_tokens': 220, 'output_tokens': 75, 'total_tokens': 295, 'interaction_type': 'investigation'},
            # MCP 5 - Successful collect_system_info call (stores actual result, then triggers summarization)
            {'type': 'mcp', 'position': 5, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'collect_system_info', 'server_name': 'test-data-server'},
            # LLM 4 - Summarization of large system info result (separate LLM call after MCP interaction stored)
            # The summarization interaction now happens AFTER the MCP interaction is stored to DB with actual result
            {'type': 'llm', 'position': 4, 'success': True, 'conversation': EXPECTED_DATA_COLLECTION_SUMMARIZATION_CONVERSATION, 'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'interaction_type': 'summarization'},
            # LLM 5 - Fourth ReAct iteration (kubectl events call) - continues after system info (investigation type)
            {'type': 'llm', 'position': 5, 'success': True, 'conversation_index': 9, 'input_tokens': 200, 'output_tokens': 60, 'total_tokens': 260, 'interaction_type': 'investigation'},
            # MCP 6 - Successful kubectl_get events call
            {'type': 'mcp', 'position': 6, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 6 - Final completion with events observation (final_analysis type)
            {'type': 'llm', 'position': 6, 'success': True, 'conversation_index': 11, 'input_tokens': 315, 'output_tokens': 125, 'total_tokens': 440, 'interaction_type': 'final_analysis'}
        ]
    },
    'verification': {
        'llm_count': 2,
        'mcp_count': 2,  # Tool discovery calls + tool execution calls are all tracked as MCP interactions
        'interactions': [
            # MCP 1 - Tool list discovery (first interaction)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # LLM 1 - Initial ReAct iteration (investigation type)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 190, 'output_tokens': 70, 'total_tokens': 260, 'interaction_type': 'investigation'},
            # MCP 2 - Successful kubectl_get attempt
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer (final_analysis type)
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 280, 'output_tokens': 110, 'total_tokens': 390, 'interaction_type': 'final_analysis'}
        ]
    },
    'analysis': {
        'llm_count': 1,
        'mcp_count': 0,
        'interactions': [
            # LLM 1 - Final analysis (final_analysis type, explicit from ReactFinalAnalysisController)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 420, 'output_tokens': 180, 'total_tokens': 600, 'interaction_type': 'final_analysis'}
        ]
    }
}

"""
Expected session-level interactions (not associated with any stage).

These interactions occur after all stages complete, such as the executive summary
generated for dashboard display and external notifications.

Format is the same as stage interactions above.
"""
EXPECTED_SESSION_LEVEL_INTERACTIONS = {
    'llm_count': 1,  # Executive summary
    'mcp_count': 0,  # No MCP interactions at session level
    'interactions': [
        # LLM 1 - Executive summary generation (final_analysis_summary type)
        {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'interaction_type': 'final_analysis_summary'}
    ]
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

# Expected conversation for session-level executive summary
EXPECTED_EXECUTIVE_SUMMARY_CONVERSATION = {
    "messages": [
        {
            "role": "system",
            "content": "You are an expert Site Reliability Engineer assistant that creates concise 1-4 line executive summaries of incident analyses for alert notifications. Focus on clarity, brevity, and actionable information."
        },
        {
            "role": "user",
            "content": """Generate a 1-4 line executive summary of this incident analysis.

CRITICAL RULES:
- Only summarize what is EXPLICITLY stated in the analysis
- Do NOT infer future actions or recommendations not mentioned
- Do NOT add your own conclusions
- Focus on: what happened, current status, and ONLY stated next steps

Analysis to summarize:

=================================================================================
Based on previous stages, the namespace is stuck due to finalizers.
=================================================================================

Executive Summary (1-4 lines, facts only):"""
        },
        {
            "role": "assistant",
            "content": "The namespace stuck-namespace is in Terminating state due to finalizers blocking deletion."
        }
    ]
}

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
- **IMPORTANT: In multi-cluster environments** (when the 'configuration_contexts_list' tool is available):
  * ALWAYS start by calling 'configuration_contexts_list' to see all available contexts and their server URLs
  * Use this information to determine which context to target before performing any operations
  * This prevents working on the wrong cluster and helps you understand the environment
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- If you get "server could not find the requested resource" error, check if you're using the namespace parameter correctly:
  * Cluster-scoped resources (Namespace, Node, ClusterRole, PersistentVolume) should NOT have a namespace parameter
  * Namespace-scoped resources (Pod, Deployment, Service, ConfigMap) REQUIRE a namespace parameter

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

You are an SRE agent using the ReAct framework to analyze Kubernetes incidents. Reason step by step, act with tools, observe results, and repeat until you identify root cause and resolution steps.

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

**Preventive Measures:** Ensure cleanup scripts remove finalizers when deleting namespaces programmatically.

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
  "contact": "__MASKED_EMAIL__",
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
            "content": """Observation: kubernetes-server.kubectl_describe error: Tool execution failed: Failed to call tool kubectl_describe on kubernetes-server: Type=McpError | Message=tool 'kubectl_describe' not found: tool not found | error=ErrorData(code=-32602, message="tool 'kubectl_describe' not found: tool not found", data=None)"""
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
- **IMPORTANT: In multi-cluster environments** (when the 'configuration_contexts_list' tool is available):
  * ALWAYS start by calling 'configuration_contexts_list' to see all available contexts and their server URLs
  * Use this information to determine which context to target before performing any operations
  * This prevents working on the wrong cluster and helps you understand the environment
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- If you get "server could not find the requested resource" error, check if you're using the namespace parameter correctly:
  * Cluster-scoped resources (Namespace, Node, ClusterRole, PersistentVolume) should NOT have a namespace parameter
  * Namespace-scoped resources (Pod, Deployment, Service, ConfigMap) REQUIRE a namespace parameter

You are an SRE agent using the ReAct framework to analyze Kubernetes incidents. Reason step by step, act with tools, observe results, and repeat until you identify root cause and resolution steps.

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

**Preventive Measures:** Ensure cleanup scripts remove finalizers when deleting namespaces programmatically.

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
  "contact": "__MASKED_EMAIL__",
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
  "contact": "__MASKED_EMAIL__",
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
Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion.
<!-- Analysis Result END -->

### Results from 'verification' stage:

#### Analysis Result

<!-- Analysis Result START -->
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

# Expected conversations for chat follow-ups
# Chat Message 1: "Can you check the pods in the stuck-namespace?"
EXPECTED_CHAT_MESSAGE_1_CONVERSATION = {
    "messages": [
        {
            "role": "system",
            "content": """## Chat Assistant Instructions

You are an expert Site Reliability Engineer (SRE) assistant helping with follow-up questions about a completed alert investigation.

The user has reviewed the investigation results and has follow-up questions. Your role is to:
- Provide clear, actionable answers based on the investigation history
- Use available tools to gather fresh, real-time data when needed
- Reference specific findings from the original investigation when relevant
- Maintain the same professional SRE communication style
- Be concise but thorough in your responses

You have access to the same tools and systems that were used in the original investigation.

## Agent-Specific Instructions

## Response Guidelines

1. **Context Awareness**: Reference the investigation history when it provides relevant context
2. **Fresh Data**: Use tools to gather current system state if the question requires up-to-date information
3. **Clarity**: If the question is ambiguous or unclear, ask for clarification in your Final Answer
4. **Specificity**: Always reference actual data and observations, not assumptions
5. **Brevity**: Be concise but complete - users have already read the full investigation

You are an SRE agent using the ReAct framework to analyze Kubernetes incidents. Reason step by step, act with tools, observe results, and repeat until you identify root cause and resolution steps.

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

**Preventive Measures:** Ensure cleanup scripts remove finalizers when deleting namespaces programmatically.

Focus on answering follow-up questions about a completed investigation for human operators to execute."""
        },
        {
            "role": "user",
            # Load investigation history from external file for maintainability
            "content": load_chat_message_template("chat_msg1_user_history.txt")
        },
        {
            "role": "assistant",
            "content": """Thought: The user wants to see the pods in stuck-namespace. I'll use kubectl_get to list them.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "stuck-namespace"}"""
        },
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "No pods found in namespace stuck-namespace"
}"""
        },
        {
            "role": "assistant",
            "content": """Final Answer: I checked the pods in stuck-namespace and found no pods are currently running. This is consistent with the namespace being stuck in Terminating state - all pods have likely been deleted already, but the namespace can't complete deletion due to the finalizers mentioned in the original investigation."""
        }
    ]
}

# Chat Message 2: "Does the namespace still exist?" (follow-up on message 1)
EXPECTED_CHAT_MESSAGE_2_CONVERSATION = {
    "messages": [
        {
            "role": "system",
            "content": """## Chat Assistant Instructions

You are an expert Site Reliability Engineer (SRE) assistant helping with follow-up questions about a completed alert investigation.

The user has reviewed the investigation results and has follow-up questions. Your role is to:
- Provide clear, actionable answers based on the investigation history
- Use available tools to gather fresh, real-time data when needed
- Reference specific findings from the original investigation when relevant
- Maintain the same professional SRE communication style
- Be concise but thorough in your responses

You have access to the same tools and systems that were used in the original investigation.

## Agent-Specific Instructions

## Response Guidelines

1. **Context Awareness**: Reference the investigation history when it provides relevant context
2. **Fresh Data**: Use tools to gather current system state if the question requires up-to-date information
3. **Clarity**: If the question is ambiguous or unclear, ask for clarification in your Final Answer
4. **Specificity**: Always reference actual data and observations, not assumptions
5. **Brevity**: Be concise but complete - users have already read the full investigation

You are an SRE agent using the ReAct framework to analyze Kubernetes incidents. Reason step by step, act with tools, observe results, and repeat until you identify root cause and resolution steps.

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

**Preventive Measures:** Ensure cleanup scripts remove finalizers when deleting namespaces programmatically.

Focus on answering follow-up questions about a completed investigation for human operators to execute."""
        },
        {
            "role": "user",
            # Load investigation history + first chat exchange from external file
            "content": load_chat_message_template("chat_msg2_user_history.txt")
        },
        {
            "role": "assistant",
            "content": """Thought: The user wants to know if the namespace still exists. Let me check its current status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
        },
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}"""
        },
        {
            "role": "assistant",
            "content": """Final Answer: Yes, the namespace still exists and remains in Terminating state. Based on the investigation history, the namespace is blocked by finalizers (kubernetes.io/pvc-protection). To resolve this, you would need to manually remove the finalizers using kubectl patch or edit the namespace resource directly."""
        }
    ]
}

# Expected final analysis endpoint responses (normalized)
# These are compared as-is after normalizing timestamps and session_id
EXPECTED_FINAL_ANALYSIS_LLM_ONLY = {
    'final_analysis': '# Alert Analysis Report\n\n**Alert Type:** test-kubernetes\n**Processing Chain:** kubernetes-namespace-terminating-chain\n**Stages:** 3\n**Environment:** production\n**Severity:** warning\n**Timestamp:** {TIMESTAMP}\n\n## Analysis\n\nBased on previous stages, the namespace is stuck due to finalizers.\n\n---\n*Processed through 3 stages*',
    'final_analysis_summary': 'The namespace stuck-namespace is in Terminating state due to finalizers blocking deletion.',
    'session_id': '{SESSION_ID}',
    'status': 'completed',
    'llm_conversation': {
        'model_name': 'gpt-5',
        'provider': 'openai-default',
        'timestamp_us': '{TIMESTAMP_US}',
        'input_tokens': 420,
        'output_tokens': 180,
        'total_tokens': 600,
        'messages': [
            {
                'role': 'system',
                'content': EXPECTED_ANALYSIS_CONVERSATION['messages'][0]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_ANALYSIS_CONVERSATION['messages'][1]['content']
            },
            {
                'role': 'assistant',
                'content': 'Based on previous stages, the namespace is stuck due to finalizers.'
            }
        ]
    },
    'chat_conversation': None,
    'alert_data': {
        'annotations': {
            'finalizers': 'kubernetes.io/pv-protection'
        },
        'cluster': 'test-cluster',
        'contact': '__MASKED_EMAIL__',
        'description': 'Namespace stuck in Terminating state',
        'labels': {
            'env': 'test', 
            'team': 'platform'
        },
        'namespace': 'test-namespace'
    }
}

EXPECTED_FINAL_ANALYSIS_WITH_CHAT = {
    'final_analysis': '# Alert Analysis Report\n\n**Alert Type:** test-kubernetes\n**Processing Chain:** kubernetes-namespace-terminating-chain\n**Stages:** 3\n**Environment:** production\n**Severity:** warning\n**Timestamp:** {TIMESTAMP}\n\n## Analysis\n\nBased on previous stages, the namespace is stuck due to finalizers.\n\n---\n*Processed through 3 stages*',
    'final_analysis_summary': 'The namespace stuck-namespace is in Terminating state due to finalizers blocking deletion.',
    'session_id': '{SESSION_ID}',
    'status': 'completed',
    'llm_conversation': {
        'model_name': 'gpt-5',
        'provider': 'openai-default',
        'timestamp_us': '{TIMESTAMP_US}',
        'input_tokens': 420,
        'output_tokens': 180,
        'total_tokens': 600,
        'messages': [
            {
                'role': 'system',
                'content': EXPECTED_ANALYSIS_CONVERSATION['messages'][0]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_ANALYSIS_CONVERSATION['messages'][1]['content']
            },
            {
                'role': 'assistant',
                'content': 'Based on previous stages, the namespace is stuck due to finalizers.'
            }
        ]
    },
    'chat_conversation': {
        'model_name': 'gpt-5',
        'provider': 'openai-default',
        'timestamp_us': '{TIMESTAMP_US}',
        'input_tokens': 220,
        'output_tokens': 95,
        'total_tokens': 315,
        'messages': [
            {
                'role': 'system',
                'content': EXPECTED_CHAT_MESSAGE_2_CONVERSATION['messages'][0]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_CHAT_MESSAGE_2_CONVERSATION['messages'][1]['content']
            },
            {
                'role': 'assistant',
                'content': EXPECTED_CHAT_MESSAGE_2_CONVERSATION['messages'][2]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_CHAT_MESSAGE_2_CONVERSATION['messages'][3]['content']
            },
            {
                'role': 'assistant',
                'content': EXPECTED_CHAT_MESSAGE_2_CONVERSATION['messages'][4]['content']
            }
        ]
    },
    'alert_data': {
        'annotations': {
            'finalizers': 'kubernetes.io/pv-protection'
        },
        'cluster': 'test-cluster',
        'contact': '__MASKED_EMAIL__',
        'description': 'Namespace stuck in Terminating state',
        'labels': {
            'env': 'test', 
            'team': 'platform'
        },
        'namespace': 'test-namespace'
    }
}


# Expected interactions structure for chat messages (similar to EXPECTED_STAGES)
EXPECTED_CHAT_INTERACTIONS = {
    'message_1': {
        'llm_count': 2,  # Initial ReAct + Final answer
        'mcp_count': 3,  # 2 tool_list discoveries + 1 tool_call
        'interactions': [
            # MCP 1 - Tool list discovery for kubernetes-server
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # MCP 2 - Tool list discovery for test-data-server
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Initial ReAct iteration (kubectl_get for pods)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 150, 'output_tokens': 60, 'total_tokens': 210},
            # MCP 3 - kubectl_get pods call
            {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 180, 'output_tokens': 90, 'total_tokens': 270}
        ]
    },
    'message_2': {
        'llm_count': 2,  # Initial ReAct + Final answer
        'mcp_count': 3,  # 2 tool_list discoveries + 1 tool_call
        'interactions': [
            # MCP 1 - Tool list discovery for kubernetes-server
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # MCP 2 - Tool list discovery for test-data-server
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Initial ReAct iteration (kubectl_get for namespace)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 200, 'output_tokens': 70, 'total_tokens': 270},
            # MCP 3 - kubectl_get namespace call
            {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 220, 'output_tokens': 95, 'total_tokens': 315}
        ]
    }
}
