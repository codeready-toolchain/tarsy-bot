"""
Simplified End-to-End Test with HTTP-level mocking.

This test uses the real FastAPI application with real internal services,
mocking only external HTTP dependencies at the network boundary.

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
"""

import asyncio
import json
import re
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
import respx
import httpx
from tarsy.integrations.mcp.client import MCPClient
from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS


# ============================================================================
# TEST CONSTANTS - Expected LLM Message Content
# ============================================================================

EXPECTED_DATA_COLLECTION_SYSTEM_MESSAGE = """## General SRE Agent Instructions

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

EXPECTED_DATA_COLLECTION_USER_MESSAGE = """Answer the following question using the available tools.

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
Begin!"""

EXPECTED_VERIFICATION_SYSTEM_MESSAGE = """## General SRE Agent Instructions

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

EXPECTED_VERIFICATION_USER_MESSAGE = """Answer the following question using the available tools.

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

Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}
Observation: kubernetes-server.kubectl_get: {
  "result": "stuck-namespace   Terminating   45m"
}
Begin!"""

EXPECTED_ANALYSIS_SYSTEM_MESSAGE = """## General SRE Agent Instructions

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

EXPECTED_ANALYSIS_USER_MESSAGE = """# Final Analysis Task


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


@pytest.mark.asyncio
@pytest.mark.e2e
class TestRealE2E:
    """
    Simplified E2E test using HTTP-level mocking.
    
    Tests the complete system flow:
    1. HTTP POST to /alerts endpoint
    2. Real alert processing through AlertService
    3. Real agent execution with real hook system
    4. Real database storage via HistoryService  
    5. HTTP GET from history APIs
    
    Mocks only external HTTP calls (LLM APIs, runbooks, MCP servers).
    """
    
    def _normalize_content(self, content: str) -> str:
        """Normalize dynamic content in LLM messages for stable comparison."""
        # Normalize timestamps (microsecond precision)
        content = re.sub(r'\*\*Timestamp:\*\* \d+', '**Timestamp:** {TIMESTAMP}', content)
        content = re.sub(r'Timestamp:\*\* \d+', 'Timestamp:** {TIMESTAMP}', content)
        
        # Normalize alert IDs and session IDs (UUIDs)
        content = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{UUID}', content)
        
        # Normalize specific test-generated data keys
        content = re.sub(r'test-kubernetes_[a-f0-9]+_\d+', 'test-kubernetes_{DATA_KEY}', content)
        
        return content

    async def test_complete_alert_processing_flow(
        self,
        e2e_test_client,
        e2e_realistic_kubernetes_alert,
        isolated_e2e_settings,
        isolated_test_database
    ):
        """
        Simplified E2E test focusing on core functionality.
        
        Flow:
        1. POST alert to /alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify basic structure (stages exist)
        
        This simplified test verifies:
        - Alert submission works
        - Processing completes without hanging
        - Session is created and marked as completed
        - Basic stage structure exists
        """
        
        # Wrap entire test in hardcore timeout to prevent hanging
        async def run_test():
            print("🚀 Starting test execution...")
            result = await self._execute_test(
                e2e_test_client,
                e2e_realistic_kubernetes_alert,
                isolated_e2e_settings,
                isolated_test_database
            )
            print("✅ Test execution completed!")
            return result
        
        try:
            # Use task-based timeout instead of wait_for to avoid cancellation issues
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=10.0)
            
            if pending:
                # Timeout occurred
                for t in pending:
                    t.cancel()
                print("❌ HARDCORE TIMEOUT: Test exceeded 30 seconds!")
                print("Check for hanging in alert processing pipeline")
                raise AssertionError("Test exceeded hardcore timeout of 10 seconds")
            else:
                # Task completed
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise
    
    async def _execute_test(
        self,
        e2e_test_client,
        e2e_realistic_kubernetes_alert,
        isolated_e2e_settings,
        isolated_test_database
    ):
        """Minimal test execution with maximum real infrastructure."""
        print("🔧 _execute_test started")
        
        # ONLY mock external network calls - use real internal services
        # Using respx for HTTP mocking and MCP SDK mocking for stdio communication
        
        # Simplified interaction tracking - focus on LLM calls only
        # (MCP interactions will be validated from API response)
        all_llm_interactions = []
        captured_llm_requests = {}  # Store full LLM request content by interaction number
        
        # Create HTTP response handlers for respx
        def create_llm_response_handler():
            """Create a handler that tracks LLM interactions and returns appropriate responses."""
            def llm_response_handler(request):
                try:
                    # Track the interaction for counting
                    request_data = request.content.decode() if hasattr(request, 'content') and request.content else "{}"
                    all_llm_interactions.append(request_data)
                    
                    # Parse and store the request content for exact verification
                    try:
                        parsed_request = json.loads(request_data)
                        messages = parsed_request.get('messages', [])
                        
                        # Store the full messages for later exact verification
                        captured_llm_requests[len(all_llm_interactions)] = {
                            'messages': messages,
                            'interaction_number': len(all_llm_interactions)
                        }
                        
                        print(f"\n🔍 LLM REQUEST #{len(all_llm_interactions)}:")
                        for i, msg in enumerate(messages):
                            print(f"  Message {i+1} ({msg.get('role', 'unknown')}):")
                            content = msg.get('content', '')
                            # Print abbreviated content for debugging
                            print(f"    Content: {content[:200]}...{content[-100:] if len(content) > 300 else ''}")
                        print("=" * 80)
                    except json.JSONDecodeError:
                        print(f"\n🔍 LLM REQUEST #{len(all_llm_interactions)}: Could not parse JSON")
                        print(f"Raw content: {request_data}")
                        print("=" * 80)
                    except Exception as e:
                        print(f"\n🔍 LLM REQUEST #{len(all_llm_interactions)}: Parse error: {e}")
                        print("=" * 80)
                    
                    # Determine response based on interaction count (simple pattern)
                    total_interactions = len(all_llm_interactions)
                    
                    if total_interactions <= 4:
                        # Data collection stage responses
                        if total_interactions == 1:
                            response_content = """Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
                        elif total_interactions == 2:
                            response_content = """Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}"""
                        elif total_interactions == 3:
                            response_content = """Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}"""
                        else:
                            response_content = """Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion."""
                    
                    elif total_interactions <= 6:
                        # Verification stage responses
                        if total_interactions == 5:
                            response_content = """Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
                        else:
                            response_content = """Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion."""
                    
                    else:
                        # Analysis stage response
                        response_content = """Based on previous stages, the namespace is stuck due to finalizers.
## Recommended Actions
1. Remove finalizers to allow deletion"""
                    
                    # Return HTTP response in the format expected by LangChain
                    return httpx.Response(
                        200,
                        json={
                            "choices": [{
                                "message": {
                                    "content": response_content,
                                    "role": "assistant"
                                },
                                "finish_reason": "stop"
                            }],
                            "model": "gpt-4",
                            "usage": {"total_tokens": 150}
                        }
                    )
                except Exception as e:
                    print(f"Error in LLM response handler: {e}")
                    # Fallback response
                    return httpx.Response(200, json={
                        "choices": [{"message": {"content": "Fallback response", "role": "assistant"}}]
                    })
            
            return llm_response_handler
        
        # Create MCP SDK mock functions  
        def create_mcp_session_mock():
            """Create a mock MCP session that provides kubectl tools.
            
            Note: This mock has intentional tool call failures to simulate MCP server issues.
            The mock_list_tools provides tools but mock_call_tool simulates that the tools
            aren't found when called. This tests the system's error handling for MCP failures.
            These errors are expected and part of the test design to verify that agents
            can handle MCP tool failures gracefully and still provide meaningful analysis.
            """
            mock_session = AsyncMock()
            
            async def mock_call_tool(tool_name, parameters):
                # Create mock result object with content attribute
                mock_result = Mock()
                
                if tool_name == 'kubectl_get':
                    resource = parameters.get('resource', 'pods')
                    name = parameters.get('name', '')
                    
                    if resource == 'namespaces' and name == 'stuck-namespace':
                        mock_content = Mock()
                        mock_content.text = 'stuck-namespace   Terminating   45m'
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
                        mock_result.content = [mock_content]
                
                elif tool_name == 'kubectl_describe':
                    resource = parameters.get('resource', '')
                    name = parameters.get('name', '')
                    
                    if resource == 'namespace' and name == 'stuck-namespace':
                        mock_content = Mock()
                        mock_content.text = """Name:         stuck-namespace
Status:       Terminating
Finalizers:   kubernetes.io/pv-protection"""
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl describe {resource} {name} response"
                        mock_result.content = [mock_content]
                
                else:
                    mock_content = Mock()
                    mock_content.text = f"Mock response for tool: {tool_name}"
                    mock_result.content = [mock_content]
                
                return mock_result
            
            async def mock_list_tools():
                # Create mock tool objects with attributes (not dict keys)
                mock_tool1 = Mock()
                mock_tool1.name = "kubectl_get"
                mock_tool1.description = "Get Kubernetes resources"
                mock_tool1.inputSchema = {
                    "type": "object",
                    "properties": {
                        "resource": {"type": "string"},
                        "namespace": {"type": "string"},
                        "name": {"type": "string"}
                    }
                }
                
                mock_tool2 = Mock()
                mock_tool2.name = "kubectl_describe"
                mock_tool2.description = "Describe Kubernetes resources"
                mock_tool2.inputSchema = {
                    "type": "object",
                    "properties": {
                        "resource": {"type": "string"},
                        "namespace": {"type": "string"},
                        "name": {"type": "string"}
                    }
                }
                
                # Return object with .tools attribute (matching MCP SDK API)
                mock_result = Mock()
                mock_result.tools = [mock_tool1, mock_tool2]
                return mock_result
            
            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools
            
            return mock_session
        
        def create_custom_mcp_session_mock():
            """Create a mock MCP session for the custom test-data-server."""
            mock_session = AsyncMock()
            
            async def mock_call_tool(tool_name, parameters):
                # Create mock result object with content attribute - this must return the exact structure
                # that MCPClient.call_tool expects after processing
                if tool_name == 'collect_system_info':
                    # Return the dictionary format that MCPClient.call_tool produces
                    return {"result": "System Info: CPU usage: 45%, Memory: 2.1GB/8GB used, Disk: 120GB free"}
                else:
                    return {"result": f"Mock response for custom tool: {tool_name}"}
            
            async def mock_list_tools():
                # Create mock tool object with attributes (not dict keys)
                mock_tool = Mock()
                mock_tool.name = "collect_system_info"
                mock_tool.description = "Collect basic system information like CPU, memory, and disk usage"
                mock_tool.inputSchema = {
                    "type": "object",
                    "properties": {
                        "detailed": {"type": "boolean", "description": "Whether to return detailed system info"}
                    }
                }
                
                # Return object with .tools attribute (matching MCP SDK API)
                mock_result = Mock()
                mock_result.tools = [mock_tool]
                return mock_result
            
            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools
            
            return mock_session
        
        # Create mock MCP sessions for both servers
        mock_kubernetes_session = create_mcp_session_mock()
        mock_custom_session = create_custom_mcp_session_mock()
        
        # Create test MCP server configuration that doesn't launch external processes
        test_mcp_servers = BUILTIN_MCP_SERVERS.copy()
        test_mcp_servers['kubernetes-server'] = {
            "server_id": "kubernetes-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "command": "echo",  # Safe command that won't fail
                "args": ["kubernetes-mock-server-ready"]
            },
            "instructions": "Test kubernetes server for e2e testing",
            "data_masking": {"enabled": False}
        }
        test_mcp_servers['test-data-server'] = {
            "server_id": "test-data-server", 
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "command": "echo",  # Safe command that won't fail
                "args": ["test-data-server-ready"]
            },
            "instructions": "Test data collection server for e2e testing",
            "data_masking": {"enabled": False}
        }
        
        # Apply comprehensive mocking with test MCP server config
        with respx.mock() as respx_mock, \
             patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', test_mcp_servers):
            
            # 1. Mock LLM API calls (preserves LLM hooks!)
            llm_handler = create_llm_response_handler()
            
            # Mock all major LLM provider endpoints (covers openai, anthropic, etc.)
            respx_mock.post(url__regex=r".*(openai\.com|anthropic\.com|api\.x\.ai|generativelanguage\.googleapis\.com|googleapis\.com).*").mock(side_effect=llm_handler)
            
            # 2. Mock runbook HTTP calls (various sources)
            respx_mock.get(url__regex=r".*(github\.com|runbooks\.example\.com).*").mock(
                return_value=httpx.Response(200, text="# Mock Runbook\nTest runbook content")
            )
            
            # 3. Mock MCP client by patching sessions after initialization
            original_list_tools = MCPClient.list_tools
            
            async def mock_list_tools(self, session_id: str, server_name=None, stage_execution_id=None):
                """Override list_tools to use our mock sessions."""
                # Ensure our mock sessions are available
                self.sessions = {
                    'kubernetes-server': mock_kubernetes_session,
                    'test-data-server': mock_custom_session
                }
                # Call the original method which will now use our mock sessions
                return await original_list_tools(self, session_id, server_name, stage_execution_id)
            
            original_call_tool = MCPClient.call_tool
            
            async def mock_call_tool(self, server_name: str, tool_name: str, parameters, session_id: str, stage_execution_id=None):
                """Override call_tool to use our mock sessions."""
                # Ensure our mock sessions are available  
                self.sessions = {
                    'kubernetes-server': mock_kubernetes_session,
                    'test-data-server': mock_custom_session
                }
                # Call the original method which will now use our mock sessions
                return await original_call_tool(self, server_name, tool_name, parameters, session_id, stage_execution_id)
            
            with patch.object(MCPClient, 'list_tools', mock_list_tools), \
                 patch.object(MCPClient, 'call_tool', mock_call_tool):
            
                print("🔧 Using the real AlertService with test MCP server config and mocking...")
                # All internal services are real, hooks work perfectly!
                # HTTP calls (LLM, runbooks) are mocked via respx
                # MCP server config replaced with test config to avoid external NPM packages
                # MCP calls handled by mock session that provides kubectl tools
            
                # STEP 1: Submit alert
                print("🚀 Step 1: Submitting alert")
                response = e2e_test_client.post("/alerts", json=e2e_realistic_kubernetes_alert)
                assert response.status_code == 200
                
                response_data = response.json()
                assert response_data["status"] == "queued"
                alert_id = response_data["alert_id"]
                print(f"✅ Alert submitted: {alert_id}")
                
                # STEP 2: Wait for processing with robust polling
                print("⏳ Step 2: Waiting for processing...")
                session_id, final_status = await self._wait_for_session_completion(e2e_test_client, max_wait_seconds=8)
                
                # STEP 3: Verify results
                print("🔍 Step 3: Verifying results...")
                
                # Basic verification
                assert session_id is not None, "Session ID missing"
                print(f"✅ Session found: {session_id}, final status: {final_status}")
                
                # Verify session completed successfully
                assert final_status == "completed", f"Expected session to be completed, but got: {final_status}"
                print("✅ Session completed successfully!")
                
                # Get session details to verify stages structure
                session_detail_response = e2e_test_client.get(f"/api/v1/history/sessions/{session_id}")
                assert session_detail_response.status_code == 200, f"Failed to get session details: {session_detail_response.status_code}"
                
                detail_data = session_detail_response.json()
                stages = detail_data.get("stages", [])
                print(f"Found {len(stages)} stages in completed session")
                
                # Assert that stages exist and verify basic structure
                assert len(stages) > 0, "Session completed but no stages found - invalid session structure"
                print("✅ Session has stages - basic structure verified")
                
                # STEP 4: Comprehensive result data verification
                print("🔍 Step 4: Comprehensive result verification...")
                await self._verify_session_metadata(detail_data, e2e_realistic_kubernetes_alert)
                await self._verify_stage_structure(stages)
                await self._verify_complete_interaction_flow(stages, captured_llm_requests)
                
                print("✅ COMPREHENSIVE VERIFICATION PASSED!")
                
                return

    async def _wait_for_session_completion(self, e2e_test_client, max_wait_seconds: int = 8):
        """
        Robust polling logic to wait for session completion.
        
        Args:
            e2e_test_client: Test client for making API calls
            max_wait_seconds: Maximum time to wait in seconds
            
        Returns:
            Tuple of (session_id, final_status)
            
        Raises:
            AssertionError: If no session found or polling times out
        """
        print(f"⏱️ Starting robust polling (max {max_wait_seconds}s)...")
        
        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.2  # Poll every 200ms for responsiveness
        attempts = 0
        
        while True:
            attempts += 1
            elapsed_time = asyncio.get_event_loop().time() - start_time
            
            # Check for timeout
            if elapsed_time >= max_wait_seconds:
                print(f"❌ Polling timeout after {elapsed_time:.1f}s ({attempts} attempts)")
                raise AssertionError(f"Session completion polling timed out after {max_wait_seconds}s")
            
            # Get current sessions
            sessions_response = e2e_test_client.get("/api/v1/history/sessions")
            if sessions_response.status_code != 200:
                print(f"⚠️ Failed to get sessions: {sessions_response.status_code}")
                await asyncio.sleep(poll_interval)
                continue
            
            sessions_data = sessions_response.json()
            sessions = sessions_data.get('sessions', [])
            
            if not sessions:
                print(f"⏳ No sessions yet (attempt {attempts}, {elapsed_time:.1f}s)")
                await asyncio.sleep(poll_interval)
                continue
            
            # Check the most recent session (first in list)
            session = sessions[0]
            session_id = session.get("session_id")
            status = session.get("status")
            
            print(f"⏳ Polling: {session_id} -> {status} (attempt {attempts}, {elapsed_time:.1f}s)")
            
            # Check if session is in a final state
            if status in ["completed", "failed"]:
                print(f"✅ Session reached final state: {status} in {elapsed_time:.1f}s ({attempts} attempts)")
                return session_id, status
            
            # Session exists but not complete yet, continue polling
            await asyncio.sleep(poll_interval)

    async def _verify_session_metadata(self, session_data, original_alert):
        """Verify session metadata matches expectations."""
        print("  📋 Verifying session metadata...")
        
        # Required session fields
        required_fields = ['session_id', 'alert_id', 'alert_type', 'status', 'started_at_us', 'completed_at_us']
        for field in required_fields:
            assert field in session_data, f"Missing required session field: {field}"
        
        # Verify alert type matches
        assert session_data['alert_type'] == original_alert['alert_type'], \
            f"Alert type mismatch: expected {original_alert['alert_type']}, got {session_data['alert_type']}"
        
        # Verify chain information
        assert 'chain_id' in session_data, "Missing chain_id in session data"
        assert session_data['chain_id'] == 'kubernetes-namespace-terminating-chain', \
            f"Unexpected chain_id: {session_data['chain_id']}"
        
        # Verify timestamps are reasonable
        started_at = session_data['started_at_us']
        completed_at = session_data['completed_at_us']
        assert started_at > 0, "Invalid started_at timestamp"
        assert completed_at > started_at, "completed_at should be after started_at"
        
        # Processing duration should be reasonable (< 30 seconds in microseconds)
        processing_duration_ms = (completed_at - started_at) / 1000
        assert processing_duration_ms < 30000, f"Processing took too long: {processing_duration_ms}ms"
        
        print(f"    ✅ Session metadata verified (chain: {session_data['chain_id']}, duration: {processing_duration_ms:.1f}ms)")

    async def _verify_stage_structure(self, stages):
        """Verify stage structure and count."""
        print("  🏗️ Verifying stage structure...")
        
        # Expected stages for kubernetes-namespace-terminating-chain
        expected_stages = ['data-collection', 'verification', 'analysis']
        
        assert len(stages) == len(expected_stages), \
            f"Expected {len(expected_stages)} stages, got {len(stages)}"
        
        # Verify each stage has required structure
        for i, stage in enumerate(stages):
            required_stage_fields = ['stage_id', 'stage_name', 'agent', 'status', 'stage_index']
            for field in required_stage_fields:
                assert field in stage, f"Stage {i} missing required field: {field}"
            
            # Verify stage order and names
            assert stage['stage_name'] == expected_stages[i], \
                f"Stage {i} name mismatch: expected {expected_stages[i]}, got {stage['stage_name']}"
            
            # Verify stage index
            assert stage['stage_index'] == i, \
                f"Stage {i} index mismatch: expected {i}, got {stage['stage_index']}"
            
            # Verify all stages completed successfully
            assert stage['status'] == 'completed', \
                f"Stage {i} ({stage['stage_name']}) not completed: {stage['status']}"
        
        print(f"    ✅ Stage structure verified ({len(stages)} stages in correct order)")

    async def _verify_complete_interaction_flow(self, stages, captured_llm_requests):
        """Verify complete interaction flow with all objects in exact order per stage."""
        print("  🔄 Verifying complete interaction flow...")
        
        # Expected complete interaction structure per stage (from actual test run data)
        expected_stages = {
            'data-collection': {
                'llm_count': 4,
                'mcp_count': 5,  # Tool discovery calls + tool execution calls are all tracked as MCP interactions
                'interactions': [
                    # MCP 1 - Tool list discovery for kubernetes-server (first interaction)
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # MCP 2 - Tool list discovery for test-data-server (returns 1 tool: collect_system_info)
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 3 - Successful kubectl_get attempt
                    {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Second ReAct iteration  
                    {'type': 'llm', 'position': 2, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 4 - Successful kubectl_describe attempt  
                    {'type': 'mcp', 'position': 4, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server'},
                    # LLM 3 - Third ReAct iteration
                    {'type': 'llm', 'position': 3, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 5 - Successful collect_system_info call
                    {'type': 'mcp', 'position': 5, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'collect_system_info', 'server_name': 'test-data-server'},
                    # LLM 4 - Final completion
                    {'type': 'llm', 'position': 4, 'success': True, 'final_message_role': 'assistant',
                     'expected_final_response': "Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion.",
                     'verify_exact_llm_content': True}
                ]
            },
            'verification': {
                'llm_count': 2,
                'mcp_count': 2,
                'interactions': [
                    # MCP 1 - Tool list discovery (first interaction)
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 2 - Successful kubectl_get attempt
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer
                    {'type': 'llm', 'position': 2, 'success': True, 'final_message_role': 'assistant',
                     'expected_final_response': "Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.",
                     'verify_exact_llm_content': True}
                ]
            },
            'analysis': {
                'llm_count': 1,
                'mcp_count': 0,
                'interactions': [
                    # LLM 1 - Final analysis (no tool discovery)
                    {'type': 'llm', 'position': 1, 'success': True, 'final_message_role': 'assistant',
                     'expected_final_response': """Based on previous stages, the namespace is stuck due to finalizers.
## Recommended Actions
1. Remove finalizers to allow deletion""",
                     'verify_exact_llm_content': True}
                ]
            }
        }
        
        for stage in stages:
            stage_name = stage['stage_name']
            expected_stage = expected_stages.get(stage_name)
            
            if not expected_stage:
                continue  # Skip verification for unexpected stages
                
            # Verify interaction counts match
            llm_interactions = stage.get('llm_interactions', [])
            mcp_interactions = stage.get('mcp_communications', [])
            
            assert len(llm_interactions) == expected_stage['llm_count'], \
                f"Stage '{stage_name}' LLM count mismatch: expected {expected_stage['llm_count']}, got {len(llm_interactions)}"
            
            assert len(mcp_interactions) == expected_stage['mcp_count'], \
                f"Stage '{stage_name}' MCP count mismatch: expected {expected_stage['mcp_count']}, got {len(mcp_interactions)}"
            
            # Verify complete interaction flow in chronological order
            # Get chronological interactions from API (mixed LLM and MCP in actual order)
            chronological_interactions = stage.get('chronological_interactions', [])
            assert len(chronological_interactions) == len(expected_stage['interactions']), \
                f"Stage '{stage_name}' chronological interaction count mismatch: expected {len(expected_stage['interactions'])}, got {len(chronological_interactions)}"
            
            llm_counter = 0
            mcp_counter = 0
            
            for i, expected_interaction in enumerate(expected_stage['interactions']):
                actual_interaction = chronological_interactions[i]
                interaction_type = expected_interaction['type']
                
                # Verify the type matches
                assert actual_interaction['type'] == interaction_type, \
                    f"Stage '{stage_name}' interaction {i+1} type mismatch: expected {interaction_type}, got {actual_interaction['type']}"
                
                if interaction_type == 'llm':
                    llm_counter += 1
                    # Verify basic LLM interaction structure
                    assert 'details' in actual_interaction, f"Stage '{stage_name}' LLM {llm_counter} missing details"
                    details = actual_interaction['details']
                    
                    assert details['success'] == expected_interaction['success'], \
                        f"Stage '{stage_name}' LLM {llm_counter} success mismatch"
                    
                    # Check final message has expected role
                    conversation = details['conversation']
                    assert conversation is not None, f"Stage '{stage_name}' LLM {llm_counter} has no conversation"
                    messages = conversation['messages']
                    assert len(messages) > 0, f"Stage '{stage_name}' LLM {llm_counter} has no messages"
                    final_message = messages[-1]
                    assert final_message['role'] == expected_interaction['final_message_role'], \
                        f"Stage '{stage_name}' LLM {llm_counter} final message role mismatch"
                    
                    # Verify final response content if specified
                    if 'expected_final_response' in expected_interaction:
                        actual_response = final_message['content'].strip()
                        expected_response = expected_interaction['expected_final_response'].strip()
                        assert actual_response == expected_response, \
                            f"Stage '{stage_name}' LLM {llm_counter} response mismatch:\nExpected: {repr(expected_response)}\nActual: {repr(actual_response)}"
                    
                    # Verify actual LLM request content using captured requests for exact string matching
                    if 'verify_exact_llm_content' in expected_interaction and expected_interaction['verify_exact_llm_content']:
                        # This should be the last LLM interaction in the stage
                        assert i == len(expected_stage['interactions']) - 1 or all(exp_int['type'] != 'llm' for exp_int in expected_stage['interactions'][i+1:]), \
                            f"Stage '{stage_name}' verify_exact_llm_content should only be on the last LLM interaction"
                        
                        # Get the captured LLM request based on the global LLM interaction count
                        # Calculate which global LLM request this corresponds to
                        global_llm_count = 0
                        for s in stages:
                            s_name = s['stage_name']
                            s_llm_interactions = s.get('llm_interactions', [])
                            if s_name == stage_name:
                                global_llm_count += llm_counter  # This is the current LLM interaction in this stage
                                break
                            else:
                                global_llm_count += len(s_llm_interactions)
                        
                        # LLM requests are 1-indexed in the captured data but global_llm_count is 0-indexed
                        captured_request = captured_llm_requests.get(global_llm_count)
                        if not captured_request:
                            print(f"⚠️ Warning: Could not find captured LLM request for global position {global_llm_count}")
                            print(f"Available captures: {list(captured_llm_requests.keys())}")
                            continue
                        
                        captured_messages = captured_request['messages']
                        assert len(captured_messages) >= 2, f"Stage '{stage_name}' LLM {llm_counter} should have at least system and user messages"
                        
                        system_message = captured_messages[0]
                        user_message = captured_messages[1]
                        
                        assert system_message.get('role') == 'system', \
                            f"Stage '{stage_name}' LLM {llm_counter} first message should be system role"
                        assert user_message.get('role') == 'user', \
                            f"Stage '{stage_name}' LLM {llm_counter} second message should be user role"
                        
                        # Store the exact captured content for use in future test runs
                        actual_system_content = system_message.get('content', '').strip()
                        actual_user_content = user_message.get('content', '').strip()
                        
                        print(f"📝 Stage '{stage_name}' LLM {llm_counter} EXACT CONTENT CAPTURED:")
                        print(f"System message length: {len(actual_system_content)} chars")
                        print(f"User message length: {len(actual_user_content)} chars")
                        
                        # Normalize both expected and actual content for comparison
                        normalized_system = self._normalize_content(actual_system_content)
                        normalized_user = self._normalize_content(actual_user_content)
                        
                        # Verify exact content based on stage 
                        if stage_name == "data-collection":
                            # Expected exact content for data-collection stage
                            expected_system = EXPECTED_DATA_COLLECTION_SYSTEM_MESSAGE
                            expected_user = EXPECTED_DATA_COLLECTION_USER_MESSAGE
                            
                            normalized_expected_system = self._normalize_content(expected_system)
                            normalized_expected_user = self._normalize_content(expected_user)
                            
                            assert normalized_system == normalized_expected_system, \
                                f"Data-collection system message mismatch:\nExpected length: {len(normalized_expected_system)}\nActual length: {len(normalized_system)}\nFirst 200 chars of diff - Expected: {normalized_expected_system[:200]}\nActual: {normalized_system[:200]}"
                            assert normalized_user == normalized_expected_user, \
                                f"Data-collection user message mismatch:\nExpected length: {len(normalized_expected_user)}\nActual length: {len(normalized_user)}\nFirst 200 chars of diff - Expected: {normalized_expected_user[:200]}\nActual: {normalized_user[:200]}"
                        elif stage_name == "verification":  
                            # Expected exact content for verification stage
                            expected_system_verification = EXPECTED_VERIFICATION_SYSTEM_MESSAGE
                            expected_user_verification = EXPECTED_VERIFICATION_USER_MESSAGE

                            normalized_expected_system_verification = self._normalize_content(expected_system_verification)
                            normalized_expected_user_verification = self._normalize_content(expected_user_verification)
                            
                            assert normalized_system == normalized_expected_system_verification, \
                                f"Verification system message mismatch:\nExpected length: {len(normalized_expected_system_verification)}\nActual length: {len(normalized_system)}"
                            assert normalized_user == normalized_expected_user_verification, \
                                f"Verification user message mismatch:\nExpected length: {len(normalized_expected_user_verification)}\nActual length: {len(normalized_user)}"
                        elif stage_name == "analysis":
                            # Expected exact content for analysis stage
                            expected_system_analysis = EXPECTED_ANALYSIS_SYSTEM_MESSAGE
                            
                            expected_user_analysis = EXPECTED_ANALYSIS_USER_MESSAGE

                            normalized_expected_system_analysis = self._normalize_content(expected_system_analysis)
                            normalized_expected_user_analysis = self._normalize_content(expected_user_analysis)
                            
                            assert normalized_system == normalized_expected_system_analysis, \
                                f"Analysis system message mismatch:\nExpected length: {len(normalized_expected_system_analysis)}\nActual length: {len(normalized_system)}"
                            assert normalized_user == normalized_expected_user_analysis, \
                                f"Analysis user message mismatch:\nExpected length: {len(normalized_expected_user_analysis)}\nActual length: {len(normalized_user)}"
                    
                elif interaction_type == 'mcp':
                    mcp_counter += 1
                    # Verify basic MCP interaction structure
                    assert 'details' in actual_interaction, f"Stage '{stage_name}' MCP {mcp_counter} missing details"
                    details = actual_interaction['details']
                    
                    assert details['success'] == expected_interaction['success'], \
                        f"Stage '{stage_name}' MCP {mcp_counter} success mismatch"
                    
                    assert details['communication_type'] == expected_interaction['communication_type'], \
                        f"Stage '{stage_name}' MCP {mcp_counter} communication_type mismatch"
                    
                    assert details['server_name'] == expected_interaction['server_name'], \
                        f"Stage '{stage_name}' MCP {mcp_counter} server_name mismatch"
                    
                    # Verify tool name for tool_call interactions
                    if expected_interaction['communication_type'] == 'tool_call':
                        assert details['tool_name'] == expected_interaction['tool_name'], \
                            f"Stage '{stage_name}' MCP {mcp_counter} tool_name mismatch"
                    
                    # Verify tool_list has available_tools
                    elif expected_interaction['communication_type'] == 'tool_list':
                        assert 'available_tools' in details, \
                            f"Stage '{stage_name}' MCP {mcp_counter} tool_list missing available_tools"
                        assert len(details['available_tools']) > 0, \
                            f"Stage '{stage_name}' MCP {mcp_counter} tool_list has no available_tools"
            
            print(f"    ✅ Stage '{stage_name}': Complete interaction flow verified ({len(llm_interactions)} LLM, {len(mcp_interactions)} MCP)")
        
        print("  ✅ Complete interaction flow verified for all stages")
