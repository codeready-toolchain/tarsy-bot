"""
Expected stage interactions for the complete alert processing flow

Format:
<stage_name>: {
    "llm_count": <number of LLM interactions>,
    "mcp_count": <number of MCP interactions>,
    "interactions": [
        {"type": "mcp", "position": <position_among_mcp_interactions>, "communication_type": <tool_list or tool_call>, "success": <success>, "server_name": <server_name>},
        {"type": "llm", "position": <position_among_llm_interactions>, "success": <success>, "conversation_index": <the number of messages from the expected conversation that should be included in the actual conversation, starting from 0>},
    ]
}
"""
# Expected stages for the complete alert processing flow
EXPECTED_STAGES = {
    'data-collection': {
        'llm_count': 4,
        'mcp_count': 5,  # Tool discovery calls + tool execution calls are all tracked as MCP interactions
        'interactions': [
            # MCP 1 - Tool list discovery for kubernetes-server (first interaction)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # MCP 2 - Tool list discovery for test-data-server (returns 1 tool: collect_system_info)
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - Initial ReAct iteration
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3}, # first 3 messages from the expected (full) conversation should be included in the actual conversation
            # MCP 3 - Successful kubectl_get attempt
            {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Second ReAct iteration  
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5},
            # MCP 4 - Successful kubectl_describe attempt  
            {'type': 'mcp', 'position': 4, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server'},
            # LLM 3 - Third ReAct iteration
            {'type': 'llm', 'position': 3, 'success': True, 'conversation_index': 7},
            # MCP 5 - Successful collect_system_info call
            {'type': 'mcp', 'position': 5, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'collect_system_info', 'server_name': 'test-data-server'},
            # LLM 4 - Final completion
            {'type': 'llm', 'position': 4, 'success': True, 'conversation_index': 9}
        ]
    },
    'verification': {
        'llm_count': 2,
        'mcp_count': 2,
        'interactions': [
            # MCP 1 - Tool list discovery (first interaction)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            # LLM 1 - Initial ReAct iteration
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3},
            # MCP 2 - Successful kubectl_get attempt
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5}
        ]
    },
    'analysis': {
        'llm_count': 1,
        'mcp_count': 0,
        'interactions': [
            # LLM 1 - Final analysis (no tool discovery)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3}
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
kubernetes-server.kubectl_get: Get Kubernetes resources
kubernetes-server.kubectl_describe: Describe Kubernetes resources
test-data-server.collect_system_info: Collect basic system information like CPU, memory, and disk usage

Question: Investigate this test-kubernetes alert and provide stage-specific analysis.

## Alert Details

**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production
**Alert Type:** test-kubernetes
**Runbook:** https://runbooks.example.com/k8s-namespace-stuck

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
            "content": """Observation: kubernetes-server.kubectl_describe: {
  "result": "Name:         stuck-namespace\\nStatus:       Terminating\\nFinalizers:   kubernetes.io/pv-protection"
}"""
        },
        {
            "role": "assistant",
            "content": """Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}"""
        },
        # 4th LLM interaction adds observation and gets final response
        {
            "role": "user", 
            "content": """Observation: test-data-server.collect_system_info: {
  "result": "{'result': 'System Info: CPU usage: 45%, Memory: 2.1GB/8GB used, Disk: 120GB free'}"
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
kubernetes-server.kubectl_get: Get Kubernetes resources
kubernetes-server.kubectl_describe: Describe Kubernetes resources

Question: Analyze this test-kubernetes alert and provide actionable recommendations.

## Alert Details

**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production
**Alert Type:** test-kubernetes
**Runbook:** https://runbooks.example.com/k8s-namespace-stuck

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
Observation: kubernetes-server.kubectl_describe: {
  "result": "Name:         stuck-namespace\\nStatus:       Terminating\\nFinalizers:   kubernetes.io/pv-protection"
}
Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}
Observation: test-data-server.collect_system_info: {
  "result": "{'result': 'System Info: CPU usage: 45%, Memory: 2.1GB/8GB used, Disk: 120GB free'}"
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

**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production
**Alert Type:** test-kubernetes
**Runbook:** https://runbooks.example.com/k8s-namespace-stuck

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
Observation: kubernetes-server.kubectl_describe: {
  "result": "Name:         stuck-namespace\\nStatus:       Terminating\\nFinalizers:   kubernetes.io/pv-protection"
}
Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}
Observation: test-data-server.collect_system_info: {
  "result": "{'result': 'System Info: CPU usage: 45%, Memory: 2.1GB/8GB used, Disk: 120GB free'}"
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
            "content": """Based on previous stages, the namespace is stuck due to finalizers.
## Recommended Actions
1. Remove finalizers to allow deletion"""
        }
    ]
}
