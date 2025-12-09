"""
Expected conversations for parallel agent E2E tests.

This file contains expected LLM conversations for different parallel execution scenarios:
- Multi-agent parallel stages
- Replica parallel stages  
- Parallel stages followed by regular stages
- Chat after parallel execution

Each conversation structure defines the exact expected messages including system prompts,
user messages, assistant responses, and observations from MCP tool calls.
"""

# ============================================================================
# MULTI-AGENT PARALLEL STAGE (2 agents in parallel + automatic synthesis)
# ============================================================================

EXPECTED_PARALLEL_AGENT_1_CONVERSATION = {
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

## Agent-Specific Instructions

You are a Kubernetes specialist analyzing pod health and resource issues.
Focus on pod status, events, and resource constraints.

You are an SRE agent analyzing incidents. Use the available tools to investigate and provide actionable recommendations.

When you have gathered sufficient information, provide your final analysis with:
1. Root cause analysis
2. Current system state assessment
3. Specific remediation steps for human operators
4. Prevention recommendations

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-parallel-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-parallel-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test parallel execution scenario",
  "namespace": "test-namespace"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for parallel execution testing.
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
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "{\\\"result\\\": \\\"Pod pod-1 is in CrashLoopBackOff state\\\"}"
}"""
        },
        {
            "role": "assistant",
            "content": """Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace. This indicates the pod is repeatedly crashing and Kubernetes is backing off on restart attempts. Recommend checking pod logs and events for root cause."""
        }
    ]
}

EXPECTED_PARALLEL_AGENT_2_CONVERSATION = {
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

## Agent-Specific Instructions

You are a log analysis specialist focusing on application errors and patterns.
Analyze logs to identify root causes and anomalies.

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
    **Parameters**: None

2. **kubernetes-server.get_logs**: Get pod logs
    **Parameters**: None

Question: Analyze this test-parallel-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-parallel-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test parallel execution scenario",
  "namespace": "test-namespace"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for parallel execution testing.
<!-- RUNBOOK END -->
```

## Previous Stage Data
No previous stage data is available for this alert. This is the first stage of analysis.

## Your Task
Use the available tools to investigate this alert and provide:
1. Root cause analysis
2. Current system state assessment  
3. Specific remediation steps for human operators
4. Prevention recommendations

Be thorough in your investigation before providing the final answer.

Begin!"""
        },
        {
            "role": "assistant",
            "content": """Thought: I should analyze the application logs to find error patterns.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}"""
        },
        {
            "role": "user",
            "content": """Observation: kubernetes-server.get_logs: {
  "result": "{\\\"logs\\\": \\\"Error: Failed to connect to database at db.example.com:5432 - connection timeout\\\"}"
}"""
        },
        {
            "role": "assistant",
            "content": """Thought: I have analyzed the logs and found the root cause.
Final Answer: Log analysis reveals database connection timeout errors. The pod is failing because it cannot connect to the database at db.example.com:5432. This explains the CrashLoopBackOff. Recommend verifying database availability and network connectivity."""
        }
    ]
}

EXPECTED_SYNTHESIS_CONVERSATION = {
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
You are an Incident Commander synthesizing results from multiple parallel investigations.

Your task:
1. CRITICALLY EVALUATE each investigation's quality - prioritize results with strong evidence and sound reasoning
2. DISREGARD or deprioritize low-quality results that lack supporting evidence or contain logical errors
3. ANALYZE the original alert using the best available data from parallel investigations
4. INTEGRATE findings from high-quality investigations into a unified understanding
5. RECONCILE conflicting information by assessing which analysis provides better evidence
6. PROVIDE definitive root cause analysis based on the most reliable evidence
7. GENERATE actionable recommendations leveraging insights from the strongest investigations

Focus on solving the original alert/issue, not on meta-analyzing agent performance or comparing approaches."""
        },
        {
            "role": "user",
            "content": """Answer the following question using the available tools.

Available tools:

No tools available.

Question: Analyze this test-parallel-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-parallel-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test parallel execution scenario",
  "namespace": "test-namespace"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for parallel execution testing.
<!-- RUNBOOK END -->
```

## Previous Stage Data
### Results from parallel stage 'investigation':

**Parallel Execution Summary**: 2/2 agents succeeded

#### Agent 1: KubernetesAgent (google-default, native-thinking)
**Status**: completed

<!-- Analysis Result START -->
USER: Tool Result: kubernetes-server.kubectl_get:
{
  "result": "{\\"result\\": \\"Pod pod-1 is in CrashLoopBackOff state\\"}"
}

ASSISTANT: Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace. This indicates the pod is repeatedly crashing and Kubernetes is backing off on restart attempts. Recommend checking pod logs and events for root cause.
<!-- Analysis Result END -->

#### Agent 2: LogAgent (anthropic-default, react)
**Status**: completed

<!-- Analysis Result START -->
ASSISTANT: Thought: I should analyze the application logs to find error patterns.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}

USER: Observation: kubernetes-server.get_logs: {
  "result": "{\\"logs\\": \\"Error: Failed to connect to database at db.example.com:5432 - connection timeout\\"}"
}

ASSISTANT: Thought: I have analyzed the logs and found the root cause.
Final Answer: Log analysis reveals database connection timeout errors. The pod is failing because it cannot connect to the database at db.example.com:5432. This explains the CrashLoopBackOff. Recommend verifying database availability and network connectivity.
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
        {
            "role": "assistant",
            "content": """Final Answer: **Synthesis of Parallel Investigations**

Both investigations provide complementary evidence. The Kubernetes agent identified the symptom (CrashLoopBackOff), while the log agent uncovered the root cause (database connection timeout).

**Root Cause:** Pod-1 in test-namespace is crashing due to inability to connect to database at db.example.com:5432, resulting in repeated restart attempts (CrashLoopBackOff).

**Recommended Actions:**
1. Verify database service is running and accessible
2. Check network policies and firewall rules for connectivity to db.example.com:5432
3. Validate database credentials in pod configuration
4. Review database connection timeout settings in application config

**Priority:** High - Application is currently non-functional"""
        }
    ]
}

# ============================================================================
# REPLICA PARALLEL STAGE (3 replicas + automatic synthesis)
# ============================================================================

EXPECTED_REPLICA_1_CONVERSATION = {
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

## Agent-Specific Instructions

You are a Kubernetes specialist analyzing pod health and resource issues.
Focus on pod status, events, and resource constraints.

You are an SRE agent analyzing incidents. Use the available tools to investigate and provide actionable recommendations.

When you have gathered sufficient information, provide your final analysis with:
1. Root cause analysis
2. Current system state assessment
3. Specific remediation steps for human operators
4. Prevention recommendations

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-replica-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-replica-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test replica execution scenario",
  "deployment": "web-app"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for replica execution testing.
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
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "Deployment web-app has 0/3 replicas ready"
}"""
        },
        {
            "role": "assistant",
            "content": """Deployment web-app has no ready replicas (0/3). This indicates a critical availability issue. All pods may be failing to start or pass health checks."""
        }
    ]
}

EXPECTED_REPLICA_2_CONVERSATION = {
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

## Agent-Specific Instructions

You are a Kubernetes specialist analyzing pod health and resource issues.
Focus on pod status, events, and resource constraints.

You are an SRE agent analyzing incidents. Use the available tools to investigate and provide actionable recommendations.

When you have gathered sufficient information, provide your final analysis with:
1. Root cause analysis
2. Current system state assessment
3. Specific remediation steps for human operators
4. Prevention recommendations

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-replica-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-replica-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test replica execution scenario",
  "deployment": "web-app"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for replica execution testing.
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
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_get:
{
  "result": "Warning: ImagePullBackOff - Failed to pull image 'web-app:v2.0.0'"
}"""
        },
        {
            "role": "assistant",
            "content": """Events show ImagePullBackOff for web-app:v2.0.0. The deployment cannot start because the specified container image cannot be pulled. This is the root cause of the 0/3 ready replicas."""
        }
    ]
}

EXPECTED_REPLICA_3_CONVERSATION = {
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

## Agent-Specific Instructions

You are a Kubernetes specialist analyzing pod health and resource issues.
Focus on pod status, events, and resource constraints.

You are an SRE agent analyzing incidents. Use the available tools to investigate and provide actionable recommendations.

When you have gathered sufficient information, provide your final analysis with:
1. Root cause analysis
2. Current system state assessment
3. Specific remediation steps for human operators
4. Prevention recommendations

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-replica-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-replica-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test replica execution scenario",
  "deployment": "web-app"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for replica execution testing.
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
        {
            "role": "user",
            "content": """Tool Result: kubernetes-server.kubectl_describe:
{
  "result": "Image: web-app:v2.0.0, Status: ErrImagePull - Image not found in registry"
}"""
        },
        {
            "role": "assistant",
            "content": """Image web-app:v2.0.0 not found in container registry. The deployment is referencing a non-existent image version. Recommend verifying the image tag or rolling back to a known-good version."""
        }
    ]
}

EXPECTED_REPLICA_SYNTHESIS_CONVERSATION = {
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
You are an Incident Commander synthesizing results from multiple parallel investigations.

Your task:
1. CRITICALLY EVALUATE each investigation's quality - prioritize results with strong evidence and sound reasoning
2. DISREGARD or deprioritize low-quality results that lack supporting evidence or contain logical errors
3. ANALYZE the original alert using the best available data from parallel investigations
4. INTEGRATE findings from high-quality investigations into a unified understanding
5. RECONCILE conflicting information by assessing which analysis provides better evidence
6. PROVIDE definitive root cause analysis based on the most reliable evidence
7. GENERATE actionable recommendations leveraging insights from the strongest investigations

Focus on solving the original alert/issue, not on meta-analyzing agent performance or comparing approaches."""
        },
        {
            "role": "user",
            "content": """Answer the following question using the available tools.

Available tools:

No tools available.

Question: Analyze this test-replica-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-replica-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test replica execution scenario",
  "deployment": "web-app"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for replica execution testing.
<!-- RUNBOOK END -->
```

## Previous Stage Data
### Results from parallel stage 'analysis':

**Parallel Execution Summary**: 3/3 agents succeeded

#### Agent 1: KubernetesAgent-1 (google-default, native-thinking)
**Status**: completed

<!-- Analysis Result START -->
Deployment web-app has no ready replicas (0/3). This indicates a critical availability issue. All pods may be failing to start or pass health checks.
<!-- Analysis Result END -->

#### Agent 2: KubernetesAgent-2 (google-default, native-thinking)
**Status**: completed

<!-- Analysis Result START -->
Events show ImagePullBackOff for web-app:v2.0.0. The deployment cannot start because the specified container image cannot be pulled. This is the root cause of the 0/3 ready replicas.
<!-- Analysis Result END -->

#### Agent 3: KubernetesAgent-3 (google-default, native-thinking)
**Status**: completed

<!-- Analysis Result START -->
Image web-app:v2.0.0 not found in container registry. The deployment is referencing a non-existent image version. Recommend verifying the image tag or rolling back to a known-good version.
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
        {
            "role": "assistant",
            "content": """Final Answer: **Synthesis of Replica Investigations**

All three replicas converged on consistent findings with increasing detail. Replica-1 identified the symptom (0/3 ready), Replica-2 found the error (ImagePullBackOff), and Replica-3 confirmed root cause (image not in registry).

**Root Cause:** Deployment web-app references non-existent image web-app:v2.0.0 in container registry, preventing all pods from starting (0/3 ready).

**Immediate Actions:**
1. Verify image web-app:v2.0.0 was successfully built and pushed to registry
2. If image missing, rollback deployment to last known-good version
3. If image exists, check image pull secrets and registry access permissions

**Preventive Measures:**
- Implement pre-deployment image existence validation
- Add automated rollback on ImagePullBackOff
- Set up alerts for failed image pulls

**Priority:** Critical - Complete service outage"""
        }
    ]
}

# ============================================================================
# PARALLEL + REGULAR STAGE (No automatic synthesis)
# ============================================================================

# KubernetesAgent conversation for parallel+regular test (with correct alert type and description)
EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_1_CONVERSATION = {
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

## Agent-Specific Instructions

You are a Kubernetes specialist analyzing pod health and resource issues.
Focus on pod status, events, and resource constraints.

You are an SRE agent analyzing incidents. Use the available tools to investigate and provide actionable recommendations.

When you have gathered sufficient information, provide your final analysis with:
1. Root cause analysis
2. Current system state assessment
3. Specific remediation steps for human operators
4. Prevention recommendations

Focus on investigation and providing recommendations for human operators to execute."""
        },
        {
            "role": "user",
            "content": """Analyze this test-parallel-regular-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-parallel-regular-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test parallel execution with regular stage",
  "namespace": "test-namespace"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for parallel execution testing.
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
        }
    ]
}

# LogAgent conversation for parallel+regular test (with correct alert type and description)
EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_2_CONVERSATION = {
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

## Agent-Specific Instructions

You are a log analysis specialist focusing on application errors and patterns.
Analyze logs to identify root causes and anomalies.

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

1. **kubernetes-server.generic_tool**: Generic test tool
    **Parameters**: None

Question: Analyze this test-parallel-regular-execution alert and provide actionable recommendations.

## Alert Details

### Alert Metadata
**Alert Type:** test-parallel-regular-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test parallel execution with regular stage",
  "namespace": "test-namespace"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for parallel execution testing.
<!-- RUNBOOK END -->
```

## Previous Stage Data
No previous stage data is available for this alert. This is the first stage of analysis.

## Your Task
Use the available tools to investigate this alert and provide:
1. Root cause analysis
2. Current system state assessment  
3. Specific remediation steps for human operators
4. Prevention recommendations

Be thorough in your investigation before providing the final answer.

Begin!"""
        }
    ]
}

EXPECTED_REGULAR_AFTER_PARALLEL_CONVERSATION = {
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
You are a command execution specialist that formulates remediation steps based on investigation results."""
        },
        {
            "role": "user",
            "content": """# Final Analysis Task


**Stage:** command (Final Analysis Stage)


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
**Alert Type:** test-parallel-regular-execution
**Severity:** warning
**Timestamp:** {TIMESTAMP}
**Environment:** production

### Alert Data
```json
{
  "description": "Test parallel execution with regular stage",
  "namespace": "test-namespace"
}
```

## Runbook Content
```markdown
<!-- RUNBOOK START -->
# Test Runbook
This is a test runbook for parallel execution testing.
<!-- RUNBOOK END -->
```

## Previous Stage Data
### Results from parallel stage 'investigation':

**Parallel Execution Summary**: 2/2 agents succeeded

#### Agent 1: KubernetesAgent (google-default, native-thinking)
**Status**: completed

<!-- Analysis Result START -->
Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace. This indicates the pod is repeatedly crashing and Kubernetes is backing off on restart attempts. Recommend checking pod logs and events for root cause.
<!-- Analysis Result END -->

#### Agent 2: LogAgent (anthropic-default, react)
**Status**: completed

<!-- Analysis Result START -->
Thought: I have analyzed the logs and found the root cause.
Final Answer: Log analysis reveals database connection timeout errors. The pod is failing because it cannot connect to the database at db.example.com:5432. This explains the CrashLoopBackOff. Recommend verifying database availability and network connectivity.
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
            "content": """Final Answer: **Remediation Commands**

Based on parallel investigations showing database connectivity issues causing CrashLoopBackOff:

**Diagnostic Commands:**
```bash
# Verify database service
kubectl get service database -n test-namespace
kubectl describe service database -n test-namespace

# Check network policies
kubectl get networkpolicies -n test-namespace

# Test database connectivity from pod
kubectl exec -n test-namespace pod-1 -- nc -zv db.example.com 5432
```

**Resolution Steps:**
1. Verify database service endpoint is correct
2. Check database is running and accepting connections
3. Review network policies for connectivity restrictions
4. Validate database credentials in ConfigMap/Secret
5. If database is external, verify firewall/security group rules

**Rollback Option:**
```bash
# If needed, rollback to previous working version
kubectl rollout undo deployment/app -n test-namespace
```"""
        }
    ]
}

# ============================================================================
# CHAT AFTER PARALLEL EXECUTION
# ============================================================================

EXPECTED_PARALLEL_CHAT_MESSAGE_1_CONVERSATION = {
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
            "content": """# Investigation History

**Alert Type:** test-parallel-execution
**Environment:** production
**Severity:** warning

**Alert Data:**
```json
{
  "description": "Test parallel execution scenario",
  "namespace": "test-namespace"
}
```

## Stage: investigation (Parallel Execution)

**Agent: KubernetesAgent**
Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace.

**Agent: LogAgent**
Log analysis reveals database connection timeout errors to db.example.com:5432.

## Stage: synthesis

**Synthesis of Parallel Investigations**
Root cause: Pod-1 crashing due to database connection timeout. Recommended verifying database service and network connectivity.

# User Question

Can you check if the database service is running?"""
        },
        {
            "role": "assistant",
            "content": """Thought: The user wants to verify database service status. I'll check the service in test-namespace.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "service", "name": "database", "namespace": "test-namespace"}"""
        },
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "Service database is running with ClusterIP 10.96.0.100"
}"""
        },
        {
            "role": "assistant",
            "content": """Final Answer: Yes, the database service is running in test-namespace with ClusterIP 10.96.0.100. The service endpoint exists, so the issue is likely with the actual database pod or external database connectivity rather than the Kubernetes service configuration."""
        }
    ]
}

EXPECTED_PARALLEL_CHAT_MESSAGE_2_CONVERSATION = {
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
            "content": """# Investigation History

**Alert Type:** test-parallel-execution
**Environment:** production
**Severity:** warning

**Alert Data:**
```json
{
  "description": "Test parallel execution scenario",
  "namespace": "test-namespace"
}
```

## Stage: investigation (Parallel Execution)

**Agent: KubernetesAgent**
Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace.

**Agent: LogAgent**
Log analysis reveals database connection timeout errors to db.example.com:5432.

## Stage: synthesis

**Synthesis of Parallel Investigations**
Root cause: Pod-1 crashing due to database connection timeout. Recommended verifying database service and network connectivity.

## Chat History

**User:** Can you check if the database service is running?

**Assistant:** Yes, the database service is running in test-namespace with ClusterIP 10.96.0.100. The service endpoint exists, so the issue is likely with the actual database pod or external database connectivity rather than the Kubernetes service configuration.

# User Question

What about the database pod itself?"""
        },
        {
            "role": "assistant",
            "content": """Thought: The user wants to check the database pod status. Let me get pod information.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "label_selector": "app=database", "namespace": "test-namespace"}"""
        },
        {
            "role": "user",
            "content": """Observation: kubernetes-server.kubectl_get: {
  "result": "Pod database-0 is in Running state, ready 1/1"
}"""
        },
        {
            "role": "assistant",
            "content": """Final Answer: The database pod (database-0) is running and ready (1/1) in test-namespace. Since both the service and pod are healthy, the issue is that pod-1 is trying to connect to the external address db.example.com:5432 instead of using the internal Kubernetes service. The application configuration likely needs to be updated to use the service name 'database' or 'database.test-namespace.svc.cluster.local' instead of the external address."""
        }
    ]
}

# Expected interactions structure for chat messages after parallel execution
# Note: Chat agents reuse tool discovery from the session, so no tool_list calls
EXPECTED_PARALLEL_CHAT_INTERACTIONS = {
    'message_1': {
        'llm_count': 2,  # Initial ReAct + Final answer
        'mcp_count': 1,  # 1 tool_call only (tools already discovered)
        'interactions': [
            # LLM 1 - Initial ReAct iteration (kubectl_get for service)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 210, 'output_tokens': 65, 'total_tokens': 275},
            # MCP 1 - kubectl_get service call
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 190, 'output_tokens': 80, 'total_tokens': 270}
        ]
    },
    'message_2': {
        'llm_count': 2,  # Initial ReAct + Final answer
        'mcp_count': 1,  # 1 tool_call only (tools already discovered)
        'interactions': [
            # LLM 1 - Initial ReAct iteration (kubectl_get for pods)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 220, 'output_tokens': 70, 'total_tokens': 290},
            # MCP 1 - kubectl_get pods call
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Final answer
            {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 200, 'output_tokens': 90, 'total_tokens': 290}
        ]
    }
}

# ============================================================================
# EXPECTED STAGES AND INTERACTION COUNTS
# ============================================================================

# Multi-agent parallel + synthesis
EXPECTED_MULTI_AGENT_STAGES = {
    "investigation": {
        "type": "parallel",
        "parallel_type": "multi_agent",
        "agent_count": 2,
        "agents": {
            "KubernetesAgent": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Native thinking with function call (no assistant message added when text_content is empty)
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 2, 'input_tokens': 245, 'output_tokens': 85, 'total_tokens': 330, 'interaction_type': 'investigation'},
                    # MCP 2 - kubectl_get tool call
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer after tool result
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 4, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245, 'interaction_type': 'final_analysis'}
                ]
            },
            "LogAgent": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 200, 'output_tokens': 75, 'total_tokens': 275, 'interaction_type': 'investigation'},
                    # MCP 2 - get_logs tool call
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'get_logs', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 190, 'output_tokens': 70, 'total_tokens': 260, 'interaction_type': 'final_analysis'}
                ]
            }
        }
    },
    "synthesis": {
        "type": "single",
        "llm_count": 1,
        "mcp_count": 0,
        "interactions": [
            # LLM 1 - Synthesis (no tools)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 420, 'output_tokens': 180, 'total_tokens': 600, 'interaction_type': 'final_analysis'}
        ]
    }
}

# Replica parallel + synthesis  
EXPECTED_REPLICA_STAGES = {
    "analysis": {
        "type": "parallel",
        "parallel_type": "replica",
        "agent_count": 3,
        "agents": {
            "KubernetesAgent-1": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call (kubectl_get deployment)
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Native thinking with function call (no assistant message added when text_content is empty)
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 2, 'input_tokens': 240, 'output_tokens': 85, 'total_tokens': 325, 'interaction_type': 'investigation'},
                    # MCP 2 - kubectl_get tool call for deployment
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer after tool result
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 4, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245, 'interaction_type': 'final_analysis'}
                ]
            },
            "KubernetesAgent-2": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call (kubectl_get events)
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Native thinking with function call (no assistant message added when text_content is empty)
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 2, 'input_tokens': 240, 'output_tokens': 80, 'total_tokens': 320, 'interaction_type': 'investigation'},
                    # MCP 2 - kubectl_get tool call for events (different from replica 1)
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer after tool result
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 4, 'input_tokens': 185, 'output_tokens': 70, 'total_tokens': 255, 'interaction_type': 'final_analysis'}
                ]
            },
            "KubernetesAgent-3": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call (kubectl_describe)
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Native thinking with function call (no assistant message added when text_content is empty)
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 2, 'input_tokens': 240, 'output_tokens': 82, 'total_tokens': 322, 'interaction_type': 'investigation'},
                    # MCP 2 - kubectl_describe tool call (different tool from replicas 1 & 2)
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer after tool result
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 4, 'input_tokens': 188, 'output_tokens': 72, 'total_tokens': 260, 'interaction_type': 'final_analysis'}
                ]
            }
        }
    },
    "synthesis": {
        "type": "single",
        "llm_count": 1,
        "mcp_count": 0,
        "interactions": [
            # LLM 1 - Synthesis (no tools)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 450, 'output_tokens': 190, 'total_tokens': 640, 'interaction_type': 'final_analysis'}
        ]
    }
}

# Parallel + regular stage (no synthesis)
EXPECTED_PARALLEL_REGULAR_STAGES = {
    "investigation": {
        "type": "parallel",
        "parallel_type": "multi_agent",
        "agent_count": 2,
        "agents": {
            "KubernetesAgent": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Native thinking with function call (no assistant message added when text_content is empty)
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 2, 'input_tokens': 240, 'output_tokens': 85, 'total_tokens': 325, 'interaction_type': 'investigation'},
                    # MCP 2 - kubectl_get tool call
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer after tool result
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 4, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245, 'interaction_type': 'final_analysis'}
                ]
            },
            "LogAgent": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 200, 'output_tokens': 75, 'total_tokens': 275, 'interaction_type': 'investigation'},
                    # MCP 2 - get_logs tool call
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'get_logs', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 190, 'output_tokens': 70, 'total_tokens': 260, 'interaction_type': 'final_analysis'}
                ]
            }
        }
    },
    "command": {
        "type": "single",
        "llm_count": 1,
        "mcp_count": 0,
        "interactions": [
            # LLM 1 - Command formulation (no tools)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 400, 'output_tokens': 170, 'total_tokens': 570, 'interaction_type': 'final_analysis'}
        ]
    }
}

# Chat after parallel
EXPECTED_PARALLEL_CHAT_STAGES = {
    "investigation": {
        "type": "parallel",
        "parallel_type": "multi_agent",
        "agent_count": 2,
        "agents": {
            "KubernetesAgent": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 245, 'output_tokens': 85, 'total_tokens': 330, 'interaction_type': 'investigation'},
                    # MCP 2 - kubectl_get tool call
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 180, 'output_tokens': 65, 'total_tokens': 245, 'interaction_type': 'final_analysis'}
                ]
            },
            "LogAgent": {
                "llm_count": 2,
                "mcp_count": 2,  # 1 tool discovery + 1 tool call
                "interactions": [
                    # MCP 1 - Tool list discovery
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 200, 'output_tokens': 75, 'total_tokens': 275, 'interaction_type': 'investigation'},
                    # MCP 2 - get_logs tool call
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'get_logs', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer
                    {'type': 'llm', 'position': 2, 'success': True, 'conversation_index': 5, 'input_tokens': 190, 'output_tokens': 70, 'total_tokens': 260, 'interaction_type': 'final_analysis'}
                ]
            }
        }
    },
    "synthesis": {
        "type": "single",
        "llm_count": 1,
        "mcp_count": 0,
        "interactions": [
            # LLM 1 - Synthesis (no tools)
            {'type': 'llm', 'position': 1, 'success': True, 'conversation_index': 3, 'input_tokens': 420, 'output_tokens': 180, 'total_tokens': 600, 'interaction_type': 'final_analysis'}
        ]
    }
}

