"""
Unit tests for PromptBuilder prompt building functionality.

Tests prompt construction, template rendering, and helper methods.
NOTE: ReAct parsing tests are now in test_react_parser.py (EP-0014).
"""

from unittest.mock import Mock

import pytest
from mcp.types import Tool

from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    AgentExecutionResult,
    ParallelStageMetadata,
    ParallelStageResult,
)
from tarsy.models.alert import ProcessingAlert
from tarsy.models.constants import SuccessPolicy, StageStatus
from tarsy.models.processing_context import (
    AvailableTools,
    ChainContext,
    StageContext,
    ToolWithServer,
)
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestPromptBuilding:
    """Test core prompt building functionality."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    @pytest.fixture
    def mock_stage_context(self):
        """Create mock StageContext with proper ToolWithServer objects for testing."""
        context = Mock()
        
        # Create proper ProcessingAlert for chain_context
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={
                'title': 'Test Alert',
                'severity': 'critical',
                'description': 'Test alert description'
            }
        )
        context.chain_context.processing_alert = processing_alert
        
        # StageContext.alert_data property returns a copy
        context.alert_data = {
            'title': 'Test Alert',
            'severity': 'critical',
            'description': 'Test alert description'
        }
        context.runbook_content = "Test runbook content"
        context.format_previous_stages_context.return_value = "No previous stage context available."
        
        # Create proper ToolWithServer objects with official MCP Tool objects
        get_pods_tool = ToolWithServer(
            server="kubectl",
            tool=Tool(
                name="get_pods",
                description="Get pod information",
                inputSchema={"type": "object", "properties": {}}
            )
        )
        
        get_namespace_tool = ToolWithServer(
            server="kubectl",
            tool=Tool(
                name="get_namespace",
                description="Get namespace info",
                inputSchema={"type": "object", "properties": {}}
            )
        )
        
        context.available_tools.tools = [get_pods_tool, get_namespace_tool]
        context.agent_name = "test-agent"
        context.mcp_servers = ["kubectl", "monitoring"]
        context.stage_name = "investigation"
        return context
    
    def test_build_standard_react_prompt_basic(self, builder, mock_stage_context):
        """Test basic standard ReAct prompt building."""
        result = builder.build_standard_react_prompt(mock_stage_context)
        
        # Should contain key ReAct elements
        assert "Test Alert" in result
        assert "critical" in result
        assert "Test runbook content" in result
        assert "**kubectl.get_pods**: Get pod information" in result
        assert "**kubectl.get_namespace**: Get namespace info" in result
        assert "Previous Stage Data" in result
    
    def test_build_standard_react_prompt_with_history(self, builder, mock_stage_context):
        """Test standard ReAct prompt with history."""
        react_history = [
            "Thought: I need to check pods",
            "Action: kubectl.get_pods",
            "Action Input: namespace=default"
        ]
        
        result = builder.build_standard_react_prompt(mock_stage_context, react_history)
        
        # Should contain history elements
        assert "Thought: I need to check pods" in result
        assert "Action: kubectl.get_pods" in result
        assert "Action Input: namespace=default" in result
    
    def test_build_stage_analysis_react_prompt_basic(self, builder, mock_stage_context):
        """Test basic stage analysis ReAct prompt building."""
        result = builder.build_stage_analysis_react_prompt(mock_stage_context)
        
        # Should contain stage-specific elements
        assert "Test Alert" in result
        assert "INVESTIGATION" in result  # Stage name in uppercase
        assert "**kubectl.get_pods**: Get pod information" in result
        assert "Previous Stage Data" in result
    
    def test_build_stage_analysis_react_prompt_with_history(self, builder, mock_stage_context):
        """Test stage analysis ReAct prompt with history."""
        react_history = ["Thought: Previous analysis step"]
        
        result = builder.build_stage_analysis_react_prompt(mock_stage_context, react_history)
        
        # Should contain history
        assert "Previous analysis step" in result
        assert "INVESTIGATION" in result
    
    def test_build_final_analysis_prompt(self, builder, mock_stage_context):
        """Test final analysis prompt building."""
        result = builder.build_final_analysis_prompt(mock_stage_context)
        
        # Should contain final analysis elements
        assert "Test Alert" in result
        assert "test-agent" in result
        assert "kubectl, monitoring" in result
        assert "investigation" in result
        assert "Final Analysis Stage" in result
        assert "Previous Stage Data" in result
    
    def test_build_final_analysis_prompt_no_stage_name(self, builder, mock_stage_context):
        """Test final analysis prompt without stage name."""
        mock_stage_context.stage_name = None
        
        result = builder.build_final_analysis_prompt(mock_stage_context)
        
        # Should still work without stage name
        assert "Test Alert" in result
        assert "test-agent" in result


@pytest.mark.unit
class TestSystemMessageGeneration:
    """Test system message generation methods."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_get_enhanced_react_system_message(self, builder):
        """Test enhanced ReAct system message generation."""
        composed_instructions = "You are a test agent with specific instructions."
        
        result = builder.get_enhanced_react_system_message(composed_instructions)
        
        # Should contain composed instructions and default task focus
        assert composed_instructions in result
        assert "investigation and providing recommendations" in result
    
    def test_get_enhanced_react_system_message_custom_task_focus(self, builder):
        """Test enhanced ReAct system message with custom task focus."""
        composed_instructions = "You are a test agent."
        custom_focus = "data collection and analysis"
        
        result = builder.get_enhanced_react_system_message(composed_instructions, custom_focus)
        
        # Should contain custom task focus
        assert composed_instructions in result
        assert custom_focus in result
    
    def test_get_general_instructions(self, builder):
        """Test general instructions generation."""
        result = builder.get_general_instructions()
        
        # Should contain key SRE instruction elements
        assert "Site Reliability Engineer" in result
        assert "Kubernetes" in result
        assert "Incident response" in result
        assert "troubleshooting" in result
        assert "root cause analysis" in result


@pytest.mark.unit
class TestHelperMethods:
    """Test helper methods for prompt building."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    @pytest.fixture
    def mock_stage_context(self):
        """Create mock StageContext."""
        context = Mock()
        context.agent_name = "test-agent"
        context.mcp_servers = ["kubectl", "monitoring", "logging"]
        return context
    
    def test_build_context_section(self, builder, mock_stage_context):
        """Test context section building."""
        result = builder._build_context_section(mock_stage_context)
        
        # Should contain agent name and server list
        assert "test-agent" in result
        assert "kubectl, monitoring, logging" in result
    
    def test_format_available_actions_with_tools(self, builder):
        """Test available actions formatting with official MCP Tool objects."""
        # Create official MCP Tool objects
        get_pods_tool = Tool(
            name="get_pods",
            description="Get pod information",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace"
                    },
                    "labels": {
                        "type": "string", 
                        "description": "Label selector"
                    }
                },
                "required": ["namespace"]
            }
        )
        
        get_metrics_tool = Tool(
            name="get_metrics",
            description="Get metrics data",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
        
        # Create ToolWithServer objects
        available_tools = [
            ToolWithServer(server="kubectl", tool=get_pods_tool),
            ToolWithServer(server="monitoring", tool=get_metrics_tool)
        ]
        
        result = builder._format_available_actions(available_tools)
        
        # Should format actions correctly with rich schema information
        assert "kubectl.get_pods" in result
        assert "Get pod information" in result
        assert "namespace (required, string): Kubernetes namespace" in result
        assert "labels (optional, string): Label selector" in result
        assert "monitoring.get_metrics" in result
        assert "Get metrics data" in result
    
    def test_format_available_actions_empty_tools(self, builder):
        """Test available actions formatting with no tools."""
        available_tools = []
        
        result = builder._format_available_actions(available_tools)
        
        assert result == "No tools available."
    
    def test_format_available_actions_empty_list(self, builder):
        """Test available actions formatting with empty tools list."""
        available_tools = []
        
        result = builder._format_available_actions(available_tools)
        
        assert result == "No tools available."
    
    def test_format_available_actions_with_enhanced_schema(self, builder):
        """Test enhanced schema formatting with all enum values displayed."""
        # Create a tool with comprehensive JSON Schema including enums
        enhanced_tool = ToolWithServer(
            server="kubectl",
            tool=Tool(
                name="get_resources",
                description="Get Kubernetes resources with various output formats",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "output_format": {
                            "type": "string",
                            "description": "Output format for the resource information",
                            "enum": ["json", "yaml", "wide", "name", "custom-columns", "custom-columns-file", "go-template", "go-template-file", "jsonpath", "jsonpath-file"],
                            "default": "yaml"
                        },
                        "resource_type": {
                            "type": "string", 
                            "description": "Type of Kubernetes resource to retrieve",
                            "enum": ["pods", "services", "deployments", "configmaps", "secrets"]
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace",
                            "default": "default",
                            "pattern": "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Request timeout in seconds",
                            "minimum": 1,
                            "maximum": 300,
                            "default": 30
                        }
                    },
                    "required": ["resource_type"]
                }
            )
        )
        
        result = builder._format_available_actions([enhanced_tool])
        
        # Test that all enum values are displayed (not truncated)
        assert 'choices: ["json", "yaml", "wide", "name", "custom-columns", "custom-columns-file", "go-template", "go-template-file", "jsonpath", "jsonpath-file"]' in result
        assert 'choices: ["pods", "services", "deployments", "configmaps", "secrets"]' in result
        
        # Test other enhanced schema features
        assert "(required, string)" in result  # Required parameter
        assert "(optional, string)" in result  # Optional parameter
        assert "(optional, integer)" in result  # Integer type
        assert "default: yaml" in result  # Default value
        assert "default: default" in result  # Default value for namespace
        assert "default: 30" in result  # Default value for timeout
        assert "pattern: ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$" in result  # Regex pattern
        assert "min: 1; max: 300" in result  # Min/max constraints
        
        # Verify no truncation indicators
        assert "..." not in result  # No truncation
        assert "choices: [json, yaml, wide, ...]" not in result  # Old truncated format should not be present
    
    def test_flatten_react_history_mixed_types(self, builder):
        """Test flattening react history with mixed types."""
        react_history = [
            "Simple string",
            ["Nested", "list", "items"],
            123,  # Non-string item
            None  # None item
        ]
        
        result = builder._flatten_react_history(react_history)
        
        # Should flatten and convert all to strings
        expected = ["Simple string", "Nested", "list", "items", "123", "None"]
        assert result == expected
    
    def test_flatten_react_history_empty(self, builder):
        """Test flattening empty react history."""
        react_history = []
        
        result = builder._flatten_react_history(react_history)
        
        assert result == []
    
    def test_flatten_react_history_strings_only(self, builder):
        """Test flattening react history with strings only."""
        react_history = ["First", "Second", "Third"]
        
        result = builder._flatten_react_history(react_history)
        
        assert result == ["First", "Second", "Third"]


@pytest.mark.unit
class TestPromptIntegration:
    """Test integration scenarios for prompt building."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    @pytest.fixture
    def full_mock_context(self):
        """Create comprehensive mock StageContext."""
        context = Mock()
        
        # Create proper ProcessingAlert for chain_context
        processing_alert = ProcessingAlert(
            alert_type="kubernetes-pod",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={
                'title': 'Pod CrashLoopBackOff',
                'severity': 'high',
                'description': 'Multiple pods crashing in production namespace',
                'labels': {'env': 'production', 'team': 'platform'}
            }
        )
        context.chain_context.processing_alert = processing_alert
        
        # StageContext.alert_data property returns a copy
        context.alert_data = {
            'title': 'Pod CrashLoopBackOff',
            'severity': 'high',
            'description': 'Multiple pods crashing in production namespace',
            'labels': {'env': 'production', 'team': 'platform'}
        }
        context.runbook_content = """
# Pod CrashLoop Investigation Runbook

## Steps:
1. Check pod status and logs
2. Verify resource limits
3. Check recent deployments
        """.strip()
        context.format_previous_stages_context.return_value = """
Stage 1 (Detection): Identified CrashLoopBackOff in prod namespace
Stage 2 (Initial): Found resource constraints and recent deployment
        """.strip()
        # Create proper ToolWithServer objects with official MCP Tool objects
        get_pods_tool = ToolWithServer(
            server="kubectl",
            tool=Tool(
                name="get_pods",
                description="List pods in namespace",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Target namespace"
                        }
                    },
                    "required": ["namespace"]
                }
            )
        )
        
        describe_pod_tool = ToolWithServer(
            server="kubectl",
            tool=Tool(
                name="describe_pod",
                description="Get detailed pod information",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Pod namespace"
                        },
                        "pod_name": {
                            "type": "string",
                            "description": "Pod name"
                        }
                    },
                    "required": ["namespace", "pod_name"]
                }
            )
        )
        
        get_logs_tool = ToolWithServer(
            server="kubectl",
            tool=Tool(
                name="get_logs",
                description="Get pod logs",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Pod namespace"
                        },
                        "pod_name": {
                            "type": "string",
                            "description": "Pod name"
                        },
                        "container": {
                            "type": "string",
                            "description": "Container name"
                        }
                    },
                    "required": ["namespace", "pod_name"]
                }
            )
        )
        
        context.available_tools.tools = [get_pods_tool, describe_pod_tool, get_logs_tool]
        context.agent_name = "kubernetes-sre-agent"
        context.mcp_servers = ["kubectl", "monitoring", "logging"]
        context.stage_name = "deep_investigation"
        return context
    
    def test_comprehensive_react_prompt_generation(self, builder, full_mock_context):
        """Test comprehensive ReAct prompt generation with all elements."""
        react_history = [
            "Thought: I need to investigate the CrashLoopBackOff issue",
            "Action: kubectl.get_pods",
            "Action Input: namespace: production",
            "Observation: Found 3 pods in CrashLoopBackOff state"
        ]
        
        result = builder.build_standard_react_prompt(full_mock_context, react_history)
        
        # Should contain all major elements
        assert "Pod CrashLoopBackOff" in result
        assert "Multiple pods crashing" in result
        assert "Pod CrashLoop Investigation Runbook" in result
        assert "Stage 1 (Detection)" in result
        assert "**kubectl.get_pods**: List pods in namespace" in result
        assert "**kubectl.describe_pod**: Get detailed pod information" in result
        assert "**kubectl.get_logs**: Get pod logs" in result
        assert "Thought: I need to investigate" in result
        assert "Found 3 pods in CrashLoopBackOff state" in result
    
    def test_stage_analysis_with_comprehensive_context(self, builder, full_mock_context):
        """Test stage analysis prompt with comprehensive context."""
        result = builder.build_stage_analysis_react_prompt(full_mock_context)
        
        # Should contain stage-specific formatting
        assert "DEEP_INVESTIGATION" in result
        assert "Pod CrashLoopBackOff" in result
        assert "**kubectl.get_pods**: List pods in namespace" in result
        assert "Stage 1 (Detection)" in result
    
    def test_final_analysis_comprehensive(self, builder, full_mock_context):
        """Test final analysis prompt with comprehensive context."""
        result = builder.build_final_analysis_prompt(full_mock_context)
        
        # Should contain final analysis elements
        assert "kubernetes-sre-agent" in result
        assert "kubectl, monitoring, logging" in result
        assert "deep_investigation" in result
        assert "Final Analysis Stage" in result
        assert "Pod CrashLoopBackOff" in result
        assert "Pod CrashLoop Investigation Runbook" in result


@pytest.mark.unit
class TestInvestigationContextFormatting:
    """Test investigation context formatting for chat."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_format_investigation_context_with_conversation(self, builder):
        """Test formatting investigation context with valid conversation."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an SRE agent"),
            LLMMessage(role=MessageRole.USER, content="Investigate pod crash in production"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Thought: I need to check the pod logs\nAction: kubectl.get_logs\nAction Input: namespace=production, pod=app-123"),
            LLMMessage(role=MessageRole.USER, content="Observation: Error: OOMKilled"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Final Answer: The pod was killed due to out-of-memory error.")
        ])
        
        result = builder.format_investigation_context(conversation)
        
        # Should contain investigation context markers
        assert "INVESTIGATION HISTORY" in result
        assert "Original Investigation" in result
        
        # Should contain user and assistant messages (but not system)
        assert "Investigate pod crash" in result
        assert "I need to check the pod logs" in result
        assert "OOMKilled" in result
        assert "Final Answer" in result
        
        # Should NOT contain system message
        assert "You are an SRE agent" not in result
    
    def test_format_investigation_context_none_conversation(self, builder):
        """Test formatting investigation context with None conversation (cancelled session)."""
        result = builder.format_investigation_context(None)
        
        # Should contain investigation context markers
        assert "INVESTIGATION HISTORY" in result
        assert "Original Investigation" in result
        
        # Should contain cancellation message
        assert "cancelled before completion" in result
        
        # Should be properly formatted
        assert "═" in result  # Contains separator lines
    
    def test_format_investigation_context_none_returns_valid_string(self, builder):
        """Test that None conversation returns valid non-empty string."""
        result = builder.format_investigation_context(None)
        
        # Should not be empty
        assert result
        assert len(result) > 0
        
        # Should be multi-line formatted text
        assert "\n" in result


@pytest.mark.unit
class TestFinalAnalysisSummaryPromptBuilding:
    """Test final analysis summary prompt building functionality."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_build_final_analysis_summary_system_prompt(self, builder):
        """Test system prompt generation for executive summary."""
        result = builder.build_final_analysis_summary_system_prompt()
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Site Reliability Engineer" in result
        assert "executive summaries" in result
        assert "concise" in result
        assert "brevity" in result
    
    def test_build_final_analysis_summary_prompt_basic(self, builder):
        """Test basic executive summary prompt generation."""
        final_analysis = "# Analysis\n\nThe pod was stuck in CrashLoopBackOff due to missing config."
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert isinstance(result, str)
        assert final_analysis in result
        assert "1-4 line" in result
        assert "executive summary" in result.lower()
    
    def test_build_final_analysis_summary_prompt_includes_rules(self, builder):
        """Test that summary prompt includes critical rules."""
        final_analysis = "Analysis content"
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert "CRITICAL RULES" in result
        assert "EXPLICITLY stated" in result
        assert "Do NOT infer" in result
        assert "Do NOT add your own conclusions" in result
        assert "facts only" in result
    
    def test_build_final_analysis_summary_prompt_with_long_analysis(self, builder):
        """Test summary prompt with very long analysis content."""
        final_analysis = "Section\n" * 500
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert final_analysis in result
        assert "executive summary" in result.lower()
    
    def test_build_final_analysis_summary_prompt_with_special_characters(self, builder):
        """Test summary prompt with special characters in analysis."""
        final_analysis = "Analysis with special chars: $VAR, {config}, [array], <tag>, & more"
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert final_analysis in result
        assert "$VAR" in result
        assert "{config}" in result
        assert "[array]" in result
    
    def test_build_final_analysis_summary_prompt_with_markdown(self, builder):
        """Test summary prompt with markdown-formatted analysis."""
        final_analysis = """# Incident Analysis

## Root Cause
The application crashed due to memory leak.

## Impact
- Service downtime: 15 minutes
- Affected users: ~1000

## Resolution
Restarted pod with increased memory limits."""
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert final_analysis in result
        assert "# Incident Analysis" in result
        assert "## Root Cause" in result
        assert "## Resolution" in result
    
    def test_build_final_analysis_summary_prompt_with_multiline_text(self, builder):
        """Test summary prompt preserves multiline structure."""
        final_analysis = "Line 1\nLine 2\nLine 3"
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert "Line 1\nLine 2\nLine 3" in result
    
    def test_build_final_analysis_summary_prompt_focuses_on_brevity(self, builder):
        """Test that prompt emphasizes brevity and conciseness."""
        final_analysis = "Analysis content"
        
        result = builder.build_final_analysis_summary_prompt(final_analysis)
        
        assert "1-4 line" in result
    
    def test_build_final_analysis_summary_system_prompt_consistency(self, builder):
        """Test that system prompt is consistent across multiple calls."""
        result1 = builder.build_final_analysis_summary_system_prompt()
        result2 = builder.build_final_analysis_summary_system_prompt()
        
        assert result1 == result2
    
    def test_build_final_analysis_summary_prompt_different_content(self, builder):
        """Test that prompt changes with different analysis content."""
        analysis1 = "Analysis 1"
        analysis2 = "Analysis 2"
        
        result1 = builder.build_final_analysis_summary_prompt(analysis1)
        result2 = builder.build_final_analysis_summary_prompt(analysis2)
        
        assert analysis1 in result1
        assert analysis2 in result2
        assert analysis1 not in result2
        assert analysis2 not in result1


@pytest.mark.unit
class TestNativeThinkingPromptBuilding:
    """Test native thinking prompt building functionality."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    @pytest.fixture
    def stage_context_first_stage(self):
        """Create StageContext for first stage (no previous results)."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={
                'title': 'Pod OOMKilled',
                'description': 'Pod restarted due to memory limit'
            }
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-123",
            current_stage_name="analysis"
        )
        chain_context.set_runbook_content("# Runbook\nCheck pod logs and memory usage")
        
        # Create mock agent
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "AnalysisAgent"
        mock_agent.mcp_servers.return_value = []
        
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    @pytest.fixture
    def stage_context_with_previous_stages(self):
        """Create StageContext with previous stage results."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={'title': 'Alert', 'description': 'Test alert'}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-456",
            current_stage_name="command"
        )
        chain_context.set_runbook_content("# Runbook\nRestart the pod")
        
        # Add previous stage result
        previous_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="AnalysisAgent",
            timestamp_us=now_us(),
            result_summary="Analysis completed",
            complete_conversation_history="Pod is in CrashLoopBackOff state"
        )
        chain_context.add_stage_result("analysis", previous_result)
        
        # Create mock agent
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "CommandAgent"
        mock_agent.mcp_servers.return_value = []
        
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    def test_build_native_thinking_prompt_first_stage(self, builder, stage_context_first_stage):
        """Test building native thinking prompt for first stage."""
        prompt = builder.build_native_thinking_prompt(stage_context_first_stage)
        
        # Check alert information is included
        assert "kubernetes" in prompt.lower()
        assert "Pod OOMKilled" in prompt or "oomkilled" in prompt.lower()
        
        # Check runbook is included
        assert "Runbook" in prompt or "runbook" in prompt.lower()
        assert "Check pod logs" in prompt or "check pod logs" in prompt.lower()
        
        # Check first stage indicator
        assert "No previous stage data" in prompt or "first stage" in prompt.lower()
    
    def test_build_native_thinking_prompt_with_previous_stages(self, builder, stage_context_with_previous_stages):
        """Test building native thinking prompt with previous stage context."""
        prompt = builder.build_native_thinking_prompt(stage_context_with_previous_stages)
        
        # Check alert information is included
        assert "kubernetes" in prompt.lower()
        
        # Check runbook is included
        assert "Restart the pod" in prompt or "restart" in prompt.lower()
        
        # Check previous stage data is included
        assert "Previous Stage Data" in prompt
        assert "CrashLoopBackOff" in prompt
    
    def test_build_native_thinking_prompt_includes_alert_section(self, builder, stage_context_first_stage):
        """Test that prompt includes formatted alert section."""
        prompt = builder.build_native_thinking_prompt(stage_context_first_stage)
        
        # Alert component should format the alert data (type and timestamp, not severity/environment)
        assert "kubernetes" in prompt.lower()
        assert "Alert Metadata" in prompt or "alert" in prompt.lower()
    
    def test_build_native_thinking_prompt_includes_runbook_section(self, builder, stage_context_first_stage):
        """Test that prompt includes formatted runbook section."""
        prompt = builder.build_native_thinking_prompt(stage_context_first_stage)
        
        # Runbook content should be included
        assert "memory usage" in prompt.lower() or "Runbook" in prompt
    
    def test_build_native_thinking_prompt_formats_previous_stages_context(
        self, builder, stage_context_with_previous_stages
    ):
        """Test that previous stages context is properly formatted."""
        prompt = builder.build_native_thinking_prompt(stage_context_with_previous_stages)
        
        # Should use the StageContext's format_previous_stages_context method
        assert "## Previous Stage Data" in prompt
        assert "Results from 'analysis' stage" in prompt or "CrashLoopBackOff" in prompt
    
    def test_build_native_thinking_prompt_handles_no_runbook(self, builder):
        """Test building prompt when runbook is None or empty."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={'title': 'Test', 'description': 'Test alert'}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-no-runbook",
            current_stage_name="analysis"
        )
        # Don't set runbook_content - leave it as None
        
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "TestAgent"
        mock_agent.mcp_servers.return_value = []
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
        
        prompt = builder.build_native_thinking_prompt(stage_context)
        
        # Should still build valid prompt
        assert "kubernetes" in prompt.lower()
        assert len(prompt) > 100
    
    def test_build_native_thinking_prompt_consistent_structure(self, builder, stage_context_first_stage):
        """Test that prompt has consistent structure across calls."""
        prompt1 = builder.build_native_thinking_prompt(stage_context_first_stage)
        prompt2 = builder.build_native_thinking_prompt(stage_context_first_stage)
        
        # Should produce identical output for same input
        assert prompt1 == prompt2
    
    def test_build_native_thinking_prompt_with_parallel_previous_stage(self, builder):
        """Test building prompt when previous stage was parallel execution."""
        timestamp = now_us()
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=timestamp,
            environment="production",
            alert_data={'title': 'Multi-perspective alert'}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-parallel",
            current_stage_name="synthesis"
        )
        chain_context.set_runbook_content("# Synthesis")
        
        # Add parallel stage result
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="KubernetesAgent",
                    timestamp_us=timestamp,
                    result_summary="K8s analysis",
                    complete_conversation_history="Pod memory exceeded"
                ),
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="VMAgent",
                    timestamp_us=timestamp,
                    result_summary="VM analysis",
                    complete_conversation_history="Node under pressure"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-p1",
                parallel_type="multi_agent",
                success_policy=SuccessPolicy.ALL,
                started_at_us=timestamp - 5000,
                completed_at_us=timestamp,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="VMAgent",
                        llm_provider="anthropic",
                        iteration_strategy="native-thinking",
                        started_at_us=timestamp - 5000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        chain_context.add_stage_result("investigation", parallel_result)
        
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "SynthesisAgent"
        mock_agent.mcp_servers.return_value = []
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
        
        prompt = builder.build_native_thinking_prompt(stage_context)
        
        # Check that parallel results are included
        assert "Previous Stage Data" in prompt
        assert "parallel stage" in prompt.lower() or "KubernetesAgent" in prompt
        assert "Pod memory exceeded" in prompt or "Node under pressure" in prompt


@pytest.mark.unit
class TestThinkingContentCorrelation:
    """Test thinking_content correlation in PromptBuilder."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_build_thinking_map_single_interaction(self, builder):
        """Test thinking map with single interaction."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        # Create interaction with one assistant message and thinking
        interaction = Mock(spec=LLMInteraction)
        interaction.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User message"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Assistant response"),
            ]
        )
        interaction.thinking_content = "My reasoning for this response"
        
        # Act
        thinking_map = builder._build_thinking_map([interaction])
        
        # Assert
        assert thinking_map == {0: "My reasoning for this response"}
    
    def test_build_thinking_map_multiple_interactions(self, builder):
        """Test thinking map with accumulating interactions."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        # First interaction: 1 assistant message
        interaction1 = Mock(spec=LLMInteraction)
        interaction1.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Message 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
            ]
        )
        interaction1.thinking_content = "Thinking for response 1"
        
        # Second interaction: 2 assistant messages (accumulative)
        interaction2 = Mock(spec=LLMInteraction)
        interaction2.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Message 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
                LLMMessage(role=MessageRole.USER, content="Message 2"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 2"),
            ]
        )
        interaction2.thinking_content = "Thinking for response 2"
        
        # Third interaction: 3 assistant messages (accumulative)
        interaction3 = Mock(spec=LLMInteraction)
        interaction3.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Message 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
                LLMMessage(role=MessageRole.USER, content="Message 2"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 2"),
                LLMMessage(role=MessageRole.USER, content="Message 3"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 3"),
            ]
        )
        interaction3.thinking_content = "Thinking for response 3"
        
        # Act
        thinking_map = builder._build_thinking_map([interaction1, interaction2, interaction3])
        
        # Assert
        assert thinking_map == {
            0: "Thinking for response 1",
            1: "Thinking for response 2",
            2: "Thinking for response 3"
        }
    
    def test_build_thinking_map_mixed_thinking(self, builder):
        """Test thinking map when some interactions have no thinking."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        # First interaction: Has thinking
        interaction1 = Mock(spec=LLMInteraction)
        interaction1.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Message 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
            ]
        )
        interaction1.thinking_content = "Thinking 1"
        
        # Second interaction: No thinking (ReAct)
        interaction2 = Mock(spec=LLMInteraction)
        interaction2.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Message 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
                LLMMessage(role=MessageRole.USER, content="Message 2"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 2"),
            ]
        )
        interaction2.thinking_content = None
        
        # Third interaction: Has thinking again
        interaction3 = Mock(spec=LLMInteraction)
        interaction3.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Message 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
                LLMMessage(role=MessageRole.USER, content="Message 2"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 2"),
                LLMMessage(role=MessageRole.USER, content="Message 3"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 3"),
            ]
        )
        interaction3.thinking_content = "Thinking 3"
        
        # Act
        thinking_map = builder._build_thinking_map([interaction1, interaction2, interaction3])
        
        # Assert
        # Only interactions with thinking_content should be in map
        assert thinking_map == {
            0: "Thinking 1",
            2: "Thinking 3"
        }
        # Index 1 should not be in map (no thinking for that response)
        assert 1 not in thinking_map
    
    def test_format_investigation_context_with_thinking(self, builder):
        """Test format_investigation_context includes thinking."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        # Create conversation
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Check pod status"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Checking pods now"),
                LLMMessage(role=MessageRole.USER, content="Tool result: Pod is crashing"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Final analysis complete"),
            ]
        )
        
        # Create interactions with thinking
        interaction1 = Mock(spec=LLMInteraction)
        interaction1.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Check pod status"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Checking pods now"),
            ]
        )
        interaction1.thinking_content = "I should start by examining the pod namespace"
        
        interaction2 = Mock(spec=LLMInteraction)
        interaction2.conversation = conversation
        interaction2.thinking_content = "Based on the crash, I should check events"
        
        # Act
        result = builder.format_investigation_context(
            conversation=conversation,
            interactions=[interaction1, interaction2],
            include_thinking=True
        )
        
        # Assert
        assert result is not None
        assert "📋 INVESTIGATION HISTORY" in result
        assert "**Internal Reasoning:**" in result
        assert "I should start by examining the pod namespace" in result
        assert "Based on the crash, I should check events" in result
        
        # Verify thinking appears BEFORE corresponding agent responses
        thinking1_pos = result.find("I should start by examining")
        response1_pos = result.find("Checking pods now")
        assert thinking1_pos < response1_pos
        
        thinking2_pos = result.find("Based on the crash")
        response2_pos = result.find("Final analysis complete")
        assert thinking2_pos < response2_pos
    
    def test_format_investigation_context_without_thinking(self, builder):
        """Test format_investigation_context excludes thinking when flag is False."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        # Create conversation
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check pod"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
            ]
        )
        
        # Create interaction with thinking
        interaction = Mock(spec=LLMInteraction)
        interaction.conversation = conversation
        interaction.thinking_content = "This thinking should NOT appear"
        
        # Act
        result = builder.format_investigation_context(
            conversation=conversation,
            interactions=[interaction],
            include_thinking=False  # Explicitly False
        )
        
        # Assert
        assert result is not None
        assert "**Internal Reasoning:**" not in result
        assert "This thinking should NOT appear" not in result
        assert "Response" in result
