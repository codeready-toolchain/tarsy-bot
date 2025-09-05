"""
Unit tests for PromptBuilder prompt building functionality.

Tests prompt construction, template rendering, and helper methods.
NOTE: ReAct parsing tests are now in test_react_parser.py (EP-0014).
"""

import pytest
from unittest.mock import Mock

from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.models.processing_context import ToolWithServer
from mcp.types import Tool


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
        context.alert_data = {
            'title': 'Test Alert',
            'severity': 'critical',
            'description': 'Test alert description'
        }
        context.runbook_content = "Test runbook content"
        context.format_previous_stages_context.return_value = "No previous stage context available."
        context.chain_context.alert_type = "kubernetes"
        
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
        context.chain_context.alert_type = "kubernetes-pod"
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
