"""
Expected conversation structures for Native Thinking E2E tests.

This module contains the expected LLM conversation message structures
for native thinking stages. Unlike ReAct tests, native thinking uses:
- Gemini's native function calling (not text parsing)
- Separate thinking content captured from model
- Different system prompts (no ReAct format instructions)

Each stage defines the exact sequence of messages (system, user, assistant)
that should appear in the conversation structure.
"""

from pathlib import Path


# Helper function to load chat message templates from external files
def load_native_thinking_chat_template(filename: str) -> str:
    """Load a chat message template from the native_thinking_chat_templates directory."""
    template_dir = Path(__file__).parent / "native_thinking_chat_templates"
    template_path = template_dir / filename
    with open(template_path, "r") as f:
        # Strip trailing newline to match actual LLM conversation format
        return f.read().rstrip('\n')


# ==============================================================================
# EXPECTED STAGES STRUCTURE
# ==============================================================================
# Format for native thinking differs from ReAct:
# - No text parsing for tool calls (uses native function calling)
# - Thinking content is captured separately
# - LLM interactions may have thinking_content field

# Expected thinking content for verification - EXACT MATCH required
# These are the complete thinking content strings that should appear in each LLM interaction
# The key is the LLM position (1-indexed) within the stage
EXPECTED_THINKING_CONTENT = {
    'data-collection': {
        # LLM 1 - Initial kubectl_get call (investigation)
        1: "The alert mentions a namespace stuck in Terminating state. I should first check the namespace status using kubectl_get to understand its current state.",
        # LLM 2 - collect_system_info call (investigation)
        2: "The namespace is in Terminating state for 45 minutes - that's quite long. I should collect more information about the system to understand if there are resource constraints affecting the cleanup.",
        # LLM 3 is summarization via LangChain - no thinking content
        # LLM 4 - kubectl_get events call (investigation)
        4: "System resources are fine - CPU, memory and disk look healthy. The issue must be with the namespace itself, possibly finalizers. Let me check events to see what's blocking the deletion.",
        # LLM 5 - Final analysis
        5: "I have gathered enough information. The namespace is stuck due to finalizers (kubernetes.io/pv-protection). I can now provide the final analysis for this data collection stage.",
    },
    'verification': {
        # LLM 1 - kubectl_get verification (investigation)
        1: "I need to verify the findings from the data collection stage by checking the current namespace status. This will confirm whether the namespace is still in Terminating state.",
        # LLM 2 - Final verification answer
        2: "The namespace is still in Terminating state after 45 minutes, confirming our findings. The finalizers (kubernetes.io/pv-protection) are indeed blocking the namespace deletion.",
    },
    'analysis': {
        # LLM 1 - Final analysis (no tools)
        1: "Synthesizing all the data from the data-collection and verification stages. The root cause is clear: kubernetes.io/pv-protection finalizers are blocking namespace deletion. The namespace has been stuck for 45 minutes.",
    },
    'chat': {
        # Chat message 1 - LLM 1 (tool call)
        'message_1_1': "User wants to see pods in the stuck-namespace. I'll use kubectl_get to list the pods and see what's running there.",
        # Chat message 1 - LLM 2 (final answer)
        'message_1_2': "No pods found in the namespace. This makes sense - the namespace is terminating and all workload pods have been cleaned up already. The finalizers are what's blocking the final deletion of the namespace itself.",
        # Chat message 2 - LLM 1 (tool call)
        'message_2_1': "User wants to know if the namespace still exists. I'll check its current status to see if it's still in Terminating or has been deleted.",
        # Chat message 2 - LLM 2 (final answer)
        'message_2_2': "The namespace still exists and is stuck in Terminating state, just as expected. I should explain the resolution steps to help the user fix this issue.",
    }
}

EXPECTED_NATIVE_THINKING_STAGES = {
    'data-collection': {
        'llm_count': 5,  # 4 regular native thinking iterations plus 1 tool result summarization
        'mcp_count': 5,  # 2 tool discovery + 3 tool calls
        'interactions': [
            # MCP 1 - Tool list discovery for kubernetes-server
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # MCP 2 - Tool list discovery for test-data-server
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Initial native thinking iteration with kubectl_get call (investigation type)
            # Conversation: [system, user] = 2 messages (no assistant msg since text_content is empty)
            # Thinking content IS present even when text_content is empty
            {'type': 'llm', 'success': True, 'conversation_index': 2, 'input_tokens': 245, 'output_tokens': 85, 'total_tokens': 330, 'interaction_type': 'investigation', 'has_thinking_content': True},
            # MCP 3 - Successful kubectl_get namespace call
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Second native thinking iteration with collect_system_info call (investigation type)
            # Conversation: [system, user, tool_result] = 3 messages
            {'type': 'llm', 'success': True, 'conversation_index': 3, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245, 'interaction_type': 'investigation', 'has_thinking_content': True},
            # MCP 4 - Successful collect_system_info call (triggers summarization)
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'collect_system_info', 'server_name': 'test-data-server'},
            # LLM 3 - Summarization of large system info result (via LangChain) - NO thinking content (LangChain, not native)
            {'type': 'llm', 'success': True, 'conversation': 'SUMMARIZATION', 'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'interaction_type': 'summarization', 'has_thinking_content': False},
            # LLM 4 - Third native thinking iteration with kubectl_get events call (investigation type)
            # Conversation: [system, user, tool_result, tool_result] = 4 messages
            {'type': 'llm', 'success': True, 'conversation_index': 4, 'input_tokens': 200, 'output_tokens': 60, 'total_tokens': 260, 'interaction_type': 'investigation', 'has_thinking_content': True},
            # MCP 5 - Successful kubectl_get events call
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 5 - Final completion with analysis (final_analysis type)
            # Conversation: [system, user, tool_result, tool_result, tool_result, assistant] = 6 messages
            {'type': 'llm', 'success': True, 'conversation_index': 6, 'input_tokens': 315, 'output_tokens': 125, 'total_tokens': 440, 'interaction_type': 'final_analysis', 'has_thinking_content': True}
        ]
    },
    'verification': {
        'llm_count': 2,
        'mcp_count': 2,
        'interactions': [
            # MCP 1 - Tool list discovery
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # LLM 1 - Initial native thinking iteration (investigation type)
            # Conversation: [system, user] = 2 messages (no assistant msg since text_content is empty)
            {'type': 'llm', 'success': True, 'conversation_index': 2, 'input_tokens': 190, 'output_tokens': 70, 'total_tokens': 260, 'interaction_type': 'investigation', 'has_thinking_content': True},
            # MCP 2 - Successful kubectl_get attempt
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            # Conversation: [system, user, tool_result, assistant] = 4 messages
            {'type': 'llm', 'success': True, 'conversation_index': 4, 'input_tokens': 280, 'output_tokens': 110, 'total_tokens': 390, 'interaction_type': 'final_analysis', 'has_thinking_content': True}
        ]
    },
    'analysis': {
        'llm_count': 1,
        'mcp_count': 1,  # Tool list discovery still happens even if no tools used
        'interactions': [
            # MCP 1 - Tool list discovery (even though analysis doesn't use tools)
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # LLM 1 - Final analysis (no tools)
            # Conversation: [system, user, assistant] = 3 messages (direct final answer)
            {'type': 'llm', 'success': True, 'conversation_index': 3, 'input_tokens': 420, 'output_tokens': 180, 'total_tokens': 600, 'interaction_type': 'final_analysis', 'has_thinking_content': True}
        ]
    }
}

# Session-level interactions (executive summary)
EXPECTED_NATIVE_THINKING_SESSION_LEVEL_INTERACTIONS = {
    'llm_count': 1,
    'mcp_count': 0,
    'interactions': [
        # LLM 1 - Executive summary generation
        {'type': 'llm', 'success': True, 'conversation_index': 3, 'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'interaction_type': 'final_analysis_summary'}
    ]
}


# ==============================================================================
# EXPECTED CONVERSATION STRUCTURES
# ==============================================================================

# Executive summary conversation (same as ReAct - it's a simple summarization task)
# Note: Uses the analysis stage final answer, not data collection
EXPECTED_NATIVE_THINKING_EXECUTIVE_SUMMARY_CONVERSATION = {
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


# Data collection stage conversation (Native Thinking format - no ReAct instructions)
# IMPORTANT: In native thinking, assistant messages are ONLY added when there's text content.
# When the model makes tool calls, it returns empty text_content, so NO assistant message is added.
# The conversation structure is: system -> user -> [tool results as user messages] -> final assistant message
EXPECTED_NATIVE_THINKING_DATA_COLLECTION_CONVERSATION = {
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

## kubernetes-server Instructions

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

## custom-server Instructions

Simple data collection server for testing - provides system information gathering tools

## Agent-Specific Instructions

You are a Kubernetes data collection specialist using Gemini's native thinking capabilities.
Your role is to gather comprehensive information about problematic resources using available kubectl tools.

Focus on:
- Namespace status and finalizers
- Pod states and termination details  
- Events showing errors and warnings
- Resource dependencies that might block cleanup

Be thorough but efficient. Collect all relevant data before stopping.

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-native-thinking alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-native-thinking
**Timestamp:** {TIMESTAMP}

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

## Your Task
Investigate this alert using the available tools and provide:
1. Root cause analysis based on your investigation
2. Current system state assessment from tool observations
3. Specific remediation steps for human operators
4. Prevention recommendations

Use tools as needed to gather information. When you have sufficient data, provide your complete analysis."""
        },
        # NOTE: No assistant message here - model called kubectl_get with empty text_content
        # Tool result 1 - kubectl_get namespace (added as user/observation message)
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "stuck-namespace   Terminating   45m"
}"""
        },
        # NOTE: No assistant message here - model called collect_system_info with empty text_content
        # Tool result 2 - collect_system_info (summarized, added as user/observation message)
        {
            "role": "user",
            "content": """Tool Result: test-data-server.collect_system_info:
{
  "result": "[NOTE: The tool output was too long and has been summarized below.]\\n\\nSummarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK.\\n\\nIMPORTANT: Re-running this tool will produce the same result. The summary above contains all critical information needed for your investigation. Use this information to proceed with your analysis rather than re-executing the same tool."
}"""
        },
        # NOTE: No assistant message here - model called kubectl_get events with empty text_content
        # Tool result 3 - kubectl_get events (added as user/observation message)
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "Mock kubectl get events response"
}"""
        },
        # LLM 4 - Final answer (only response with actual text_content, so only assistant message)
        {
            "role": "assistant",
            "content": "Based on the collected data, namespace 'stuck-namespace' is stuck in Terminating state due to finalizers blocking deletion."
        }
    ]
}


# Verification stage conversation (Native Thinking format)
# Same pattern: no assistant messages when making tool calls, only when providing final answer
EXPECTED_NATIVE_THINKING_VERIFICATION_CONVERSATION = {
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

## kubernetes-server Instructions

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

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-native-thinking alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-native-thinking
**Timestamp:** {TIMESTAMP}

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
Based on the collected data, namespace 'stuck-namespace' is stuck in Terminating state due to finalizers blocking deletion.
<!-- Analysis Result END -->


## Your Task
Investigate this alert using the available tools and provide:
1. Root cause analysis based on your investigation
2. Current system state assessment from tool observations
3. Specific remediation steps for human operators
4. Prevention recommendations

Use tools as needed to gather information. When you have sufficient data, provide your complete analysis."""
        },
        # NOTE: No assistant message here - model called kubectl_get with empty text_content
        # Tool result - kubectl_get namespace verification
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "stuck-namespace   Terminating   45m"
}"""
        },
        # LLM 2 - Final answer (only response with actual text_content)
        {
            "role": "assistant",
            "content": "Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion."
        }
    ]
}


# Analysis stage conversation (Native Thinking format - no tools)
EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION = {
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

## kubernetes-server Instructions

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

## Agent-Specific Instructions

You are a Senior Site Reliability Engineer specializing in Kubernetes troubleshooting.
Using Gemini's native thinking capabilities, analyze the collected data from previous stages 
to identify root causes.

Your analysis should:
- Synthesize information from all data collection activities
- Identify the specific root cause of the problem
- Assess the impact and urgency level
- Provide confidence levels for your conclusions

Be precise and actionable in your analysis.

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-native-thinking alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-native-thinking
**Timestamp:** {TIMESTAMP}

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
Based on the collected data, namespace 'stuck-namespace' is stuck in Terminating state due to finalizers blocking deletion.
<!-- Analysis Result END -->

### Results from 'verification' stage:

#### Analysis Result

<!-- Analysis Result START -->
Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.
<!-- Analysis Result END -->


## Your Task
Investigate this alert using the available tools and provide:
1. Root cause analysis based on your investigation
2. Current system state assessment from tool observations
3. Specific remediation steps for human operators
4. Prevention recommendations

Use tools as needed to gather information. When you have sufficient data, provide your complete analysis."""
        },
        {
            "role": "assistant",
            "content": "Based on previous stages, the namespace is stuck due to finalizers."
        }
    ]
}


# ==============================================================================
# CHAT INTERACTIONS FOR NATIVE THINKING
# ==============================================================================

# Chat interactions follow the same pattern: no assistant message when making tool calls
EXPECTED_NATIVE_THINKING_CHAT_INTERACTIONS = {
    'message_1': {
        'llm_count': 2,
        'mcp_count': 3,
        'interactions': [
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Tool call (investigation): [system, user] = 2 messages (no assistant msg)
            {'type': 'llm', 'success': True, 'conversation_index': 2, 'input_tokens': 150, 'output_tokens': 60, 'total_tokens': 210, 'interaction_type': 'investigation'},
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer: [system, user, tool_result, assistant] = 4 messages
            {'type': 'llm', 'success': True, 'conversation_index': 4, 'input_tokens': 180, 'output_tokens': 90, 'total_tokens': 270, 'interaction_type': 'final_analysis'}
        ]
    },
    'message_2': {
        'llm_count': 2,
        'mcp_count': 3,
        'interactions': [
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Tool call (investigation): [system, user] = 2 messages (no assistant msg)
            {'type': 'llm', 'success': True, 'conversation_index': 2, 'input_tokens': 200, 'output_tokens': 70, 'total_tokens': 270, 'interaction_type': 'investigation'},
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer: [system, user, tool_result, assistant] = 4 messages
            {'type': 'llm', 'success': True, 'conversation_index': 4, 'input_tokens': 220, 'output_tokens': 95, 'total_tokens': 315, 'interaction_type': 'final_analysis'}
        ]
    }
}


# Chat Message 1 conversation (Native Thinking format)
# Same pattern: no assistant message when making tool call, only when providing final answer
EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_1_CONVERSATION = {
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

Focus on answering follow-up questions about a completed investigation for human operators to execute."""
        },
        {
            "role": "user",
            "content": """═══════════════════════════════════════════════════════════════════════════════
📋 INVESTIGATION CONTEXT
═══════════════════════════════════════════════════════════════════════════════

# Original Investigation

### Initial Investigation Request

Analyze this test-native-thinking alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-native-thinking
**Timestamp:** {TIMESTAMP}

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
Based on the collected data, namespace 'stuck-namespace' is stuck in Terminating state due to finalizers blocking deletion.
<!-- Analysis Result END -->

### Results from 'verification' stage:

#### Analysis Result

<!-- Analysis Result START -->
Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.
<!-- Analysis Result END -->


## Your Task
Investigate this alert using the available tools and provide:
1. Root cause analysis based on your investigation
2. Current system state assessment from tool observations
3. Specific remediation steps for human operators
4. Prevention recommendations

Use tools as needed to gather information. When you have sufficient data, provide your complete analysis.

**Agent Response:**

Based on previous stages, the namespace is stuck due to finalizers.

═══════════════════════════════════════════════════════════════════════════════
🎯 CURRENT TASK
═══════════════════════════════════════════════════════════════════════════════

**Question:** Can you check the pods in the stuck-namespace?

**Your Task:**
Answer the user's question based on the investigation context above.
- Reference investigation history when relevant
- Use tools to get fresh data if needed
- Provide clear, actionable responses

Begin your response:"""
        },
        # NOTE: No assistant message here - model called kubectl_get pods with empty text_content
        # Tool result - kubectl_get pods
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "No pods found in namespace stuck-namespace"
}"""
        },
        # Final answer (only assistant message in this chat exchange)
        {
            "role": "assistant",
            "content": "I checked the pods in stuck-namespace and found no pods are currently running. This is consistent with the namespace being stuck in Terminating state - all pods have likely been deleted already, but the namespace can't complete deletion due to the finalizers mentioned in the original investigation."
        }
    ]
}


# Chat Message 2 conversation (Native Thinking format)
# Same pattern: no assistant message when making tool call, only when providing final answer
EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION = {
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

Focus on answering follow-up questions about a completed investigation for human operators to execute."""
        },
        {
            "role": "user",
            "content": """═══════════════════════════════════════════════════════════════════════════════
📋 INVESTIGATION CONTEXT
═══════════════════════════════════════════════════════════════════════════════

# Original Investigation

### Initial Investigation Request

Analyze this test-native-thinking alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-native-thinking
**Timestamp:** {TIMESTAMP}

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
Based on the collected data, namespace 'stuck-namespace' is stuck in Terminating state due to finalizers blocking deletion.
<!-- Analysis Result END -->

### Results from 'verification' stage:

#### Analysis Result

<!-- Analysis Result START -->
Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.
<!-- Analysis Result END -->


## Your Task
Investigate this alert using the available tools and provide:
1. Root cause analysis based on your investigation
2. Current system state assessment from tool observations
3. Specific remediation steps for human operators
4. Prevention recommendations

Use tools as needed to gather information. When you have sufficient data, provide your complete analysis.

**Agent Response:**

Based on previous stages, the namespace is stuck due to finalizers.

═══════════════════════════════════════════════════════════════════════════════
💬 CHAT HISTORY (1 previous exchange)
═══════════════════════════════════════════════════════════════════════════════

## Exchange 1

**USER:**
Can you check the pods in the stuck-namespace?

**Observation:**

Tool Result: kubernetes-server.kubectl_get:
{
  "result": "No pods found in namespace stuck-namespace"
}

**ASSISTANT:**
I checked the pods in stuck-namespace and found no pods are currently running. This is consistent with the namespace being stuck in Terminating state - all pods have likely been deleted already, but the namespace can't complete deletion due to the finalizers mentioned in the original investigation.

═══════════════════════════════════════════════════════════════════════════════
🎯 CURRENT TASK
═══════════════════════════════════════════════════════════════════════════════

**Question:** Does the namespace still exist?

**Your Task:**
Answer the user's question based on the investigation context above.
- Reference investigation history when relevant
- Use tools to get fresh data if needed
- Provide clear, actionable responses

Begin your response:"""
        },
        # NOTE: No assistant message here - model called kubectl_get with empty text_content
        # Tool result - kubectl_get namespace status
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "stuck-namespace   Terminating   45m"
}"""
        },
        # Final answer (only assistant message in this chat exchange)
        {
            "role": "assistant",
            "content": "Yes, the namespace still exists and remains in Terminating state. Based on the investigation history, the namespace is blocked by finalizers (kubernetes.io/pvc-protection). To resolve this, you would need to manually remove the finalizers using kubectl patch or edit the namespace resource directly."
        }
    ]
}


# ==============================================================================
# FINAL ANALYSIS ENDPOINT RESPONSES
# ==============================================================================

EXPECTED_NATIVE_THINKING_FINAL_ANALYSIS_LLM_ONLY = {
    'final_analysis': '# Alert Analysis Report\n\n**Alert Type:** test-native-thinking\n**Processing Chain:** native-thinking-kubernetes-chain\n**Stages:** 3\n**Timestamp:** {TIMESTAMP}\n\n## Analysis\n\nBased on previous stages, the namespace is stuck due to finalizers.\n\n---\n*Processed through 3 stages*',
    'final_analysis_summary': 'The namespace stuck-namespace is in Terminating state due to finalizers blocking deletion.',
    'session_id': '{SESSION_ID}',
    'status': 'completed',
    'llm_conversation': {
        'model_name': 'gemini-2.5-pro',
        'provider': 'google-default',
        'timestamp_us': '{TIMESTAMP_US}',
        'input_tokens': 420,
        'output_tokens': 180,
        'total_tokens': 600,
        'messages': [
            {
                'role': 'system',
                'content': EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION['messages'][0]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION['messages'][1]['content']
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

EXPECTED_NATIVE_THINKING_FINAL_ANALYSIS_WITH_CHAT = {
    'final_analysis': '# Alert Analysis Report\n\n**Alert Type:** test-native-thinking\n**Processing Chain:** native-thinking-kubernetes-chain\n**Stages:** 3\n**Timestamp:** {TIMESTAMP}\n\n## Analysis\n\nBased on previous stages, the namespace is stuck due to finalizers.\n\n---\n*Processed through 3 stages*',
    'final_analysis_summary': 'The namespace stuck-namespace is in Terminating state due to finalizers blocking deletion.',
    'session_id': '{SESSION_ID}',
    'status': 'completed',
    'llm_conversation': {
        'model_name': 'gemini-2.5-pro',
        'provider': 'google-default',
        'timestamp_us': '{TIMESTAMP_US}',
        'input_tokens': 420,
        'output_tokens': 180,
        'total_tokens': 600,
        'messages': [
            {
                'role': 'system',
                'content': EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION['messages'][0]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION['messages'][1]['content']
            },
            {
                'role': 'assistant',
                'content': 'Based on previous stages, the namespace is stuck due to finalizers.'
            }
        ]
    },
    'chat_conversation': {
        'model_name': 'gemini-2.5-pro',
        'provider': 'google-default',
        'timestamp_us': '{TIMESTAMP_US}',
        'input_tokens': 220,
        'output_tokens': 95,
        'total_tokens': 315,
        'messages': [
            {
                'role': 'system',
                'content': EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION['messages'][0]['content']
            },
            {
                'role': 'user',
                'content': EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION['messages'][1]['content']
            },
            # No assistant message for tool call - model returns empty text when making tool calls
            {
                'role': 'user',  # Tool result
                'content': EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION['messages'][2]['content']
            },
            {
                'role': 'assistant',
                'content': EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION['messages'][3]['content']
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

