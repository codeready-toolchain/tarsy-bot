"""
Unit tests for PromptBuilder.

Tests ReAct response parsing, action conversion, and error handling.
Focuses on critical functionality that ensures reliable agent communication.
"""

import json
import pytest
from unittest.mock import Mock

from tarsy.agents.prompts.builders import PromptBuilder


@pytest.mark.unit
class TestReActResponseParsing:
    """Test ReAct response parsing with various edge cases."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_parse_empty_response(self, builder):
        """Test parsing empty or None response."""
        result = builder.parse_react_response("")
        
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False
    
    def test_parse_none_response(self, builder):
        """Test parsing None response."""
        result = builder.parse_react_response(None)
        
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False
    
    def test_parse_non_string_response(self, builder):
        """Test parsing non-string response."""
        result = builder.parse_react_response(123)
        
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False
    
    def test_parse_response_with_hallucinated_observations(self, builder):
        """Test that parsing stops at hallucinated observations."""
        response = """Thought: I need to check the namespace status.
Action: kubectl.get_namespace
Action Input: name=test-namespace

Observation: Based on the kubectl command, the namespace shows:
{
  "status": "Terminating",
  "metadata": {
    "finalizers": ["example.com/finalizer"]
  }
}

Thought: I can see the issue is a stuck finalizer."""
        
        result = builder.parse_react_response(response)
        
        # Should stop parsing at the hallucinated observation
        assert result['thought'] == "I need to check the namespace status."
        assert result['action'] == "kubectl.get_namespace"
        assert result['action_input'] == "name=test-namespace"
        assert result['final_answer'] is None
        assert result['is_complete'] is False
    
    def test_parse_response_with_fake_content_marker(self, builder):
        """Test parsing stops at fake content markers."""
        response = """Thought: Need to investigate the alert.
Action: test.action
Action Input: param=value

[Based on the investigation, I found that...]

Thought: This shouldn't be parsed."""
        
        result = builder.parse_react_response(response)
        
        # Should stop at [Based on...
        assert result['thought'] == "Need to investigate the alert."
        assert result['action'] == "test.action"
        assert result['action_input'] == "param=value"
    
    def test_parse_response_with_duplicate_final_answer(self, builder):
        """Test that only first Final Answer is used."""
        response = """Thought: Analysis complete.

Final Answer: First analysis result.

Final Answer: This second one should be ignored."""
        
        result = builder.parse_react_response(response)
        
        # The first final answer should be used
        assert "First analysis result" in result['final_answer']
        assert result['is_complete'] is True
    
    def test_parse_response_with_duplicate_actions(self, builder):
        """Test that latest Action/Action Input is used."""
        response = """Thought: First thought.
Action: first.action
Action Input: first=input

Thought: Changed my mind.
Action: second.action
Action Input: second=input"""
        
        result = builder.parse_react_response(response)
        
        # Should use latest action
        assert result['action'] == "second.action"
        assert result['action_input'] == "second=input"
        assert result['thought'] == "Changed my mind."
    
    def test_parse_response_with_thought_only(self, builder):
        """Test parsing response with only 'Thought' header."""
        response = """Thought
I need to analyze this situation carefully.
This is multi-line thinking."""
        
        result = builder.parse_react_response(response)
        
        expected_thought = "I need to analyze this situation carefully.\nThis is multi-line thinking."
        assert result['thought'] == expected_thought
        assert result['action'] is None
        assert result['final_answer'] is None
    
    def test_parse_response_parsing_exception_returns_partial(self, builder):
        """Test that parsing exceptions return partial results."""
        # Mock the _finalize_current_section to raise an exception partway through
        original_method = builder._finalize_current_section
        call_count = 0
        
        def mock_finalize(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:  # Fail on second call
                raise ValueError("Simulated parsing error")
            return original_method(*args, **kwargs)
        
        builder._finalize_current_section = mock_finalize
        
        response = """Thought: This should work.
Action: test.action
Action Input: should=fail"""
        
        result = builder.parse_react_response(response)
        
        # Should return partial results even with exception
        assert isinstance(result, dict)
        assert 'thought' in result
        assert 'action' in result
        assert 'is_complete' in result


@pytest.mark.unit
class TestActionToToolCallConversion:
    """Test ReAct action to MCP tool call conversion."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_convert_simple_action(self, builder):
        """Test converting simple action to tool call."""
        result = builder.convert_action_to_tool_call(
            "kubectl.get_pods", 
            "namespace=default"
        )
        
        assert result['server'] == 'kubectl'
        assert result['tool'] == 'get_pods'
        assert result['parameters']['namespace'] == 'default'
        assert result['reason'] == 'ReAct Action: kubectl.get_pods'
    
    def test_convert_action_with_json_input(self, builder):
        """Test converting action with JSON input."""
        json_input = '{"namespace": "kube-system", "pod": "coredns"}'
        
        result = builder.convert_action_to_tool_call(
            "kubectl.describe_pod",
            json_input
        )
        
        assert result['server'] == 'kubectl'
        assert result['tool'] == 'describe_pod'
        assert result['parameters']['namespace'] == 'kube-system'
        assert result['parameters']['pod'] == 'coredns'
    
    def test_convert_action_with_yaml_like_input(self, builder):
        """Test converting action with YAML-like input."""
        yaml_input = "apiVersion: v1, kind: Namespace, name: superman-dev"
        
        result = builder.convert_action_to_tool_call(
            "kubectl.apply",
            yaml_input
        )
        
        assert result['server'] == 'kubectl'
        assert result['tool'] == 'apply'
        assert result['parameters']['apiVersion'] == 'v1'
        assert result['parameters']['kind'] == 'Namespace'
        assert result['parameters']['name'] == 'superman-dev'
    
    def test_convert_action_with_key_equals_value_input(self, builder):
        """Test converting action with key=value input."""
        input_str = "namespace=default, pod=nginx, container=app"
        
        result = builder.convert_action_to_tool_call(
            "kubectl.logs",
            input_str
        )
        
        assert result['server'] == 'kubectl'
        assert result['tool'] == 'logs'
        assert result['parameters']['namespace'] == 'default'
        assert result['parameters']['pod'] == 'nginx'
        assert result['parameters']['container'] == 'app'
    
    def test_convert_action_with_plain_text_input(self, builder):
        """Test converting action with plain text input."""
        result = builder.convert_action_to_tool_call(
            "search.query",
            "kubernetes finalizer stuck"
        )
        
        assert result['server'] == 'search'
        assert result['tool'] == 'query'
        assert result['parameters']['input'] == 'kubernetes finalizer stuck'
    
    def test_convert_action_empty_action_raises_error(self, builder):
        """Test that empty action raises ValueError."""
        with pytest.raises(ValueError, match="Action cannot be empty"):
            builder.convert_action_to_tool_call("", "some input")
    
    def test_convert_action_no_dot_raises_error(self, builder):
        """Test that action without dot raises ValueError."""
        with pytest.raises(ValueError, match="Action must be in format 'server.tool'"):
            builder.convert_action_to_tool_call("invalid_action", "some input")
    
    def test_convert_action_with_invalid_json_fallback(self, builder):
        """Test fallback when JSON parsing fails."""
        invalid_json = '{"namespace": invalid json'
        
        result = builder.convert_action_to_tool_call(
            "test.action",
            invalid_json
        )
        
        # Should fallback - might parse parts or use as input
        assert 'parameters' in result
        assert result['server'] == 'test'
        assert result['tool'] == 'action'
    
    def test_convert_action_with_mixed_format_input(self, builder):
        """Test converting action with mixed format input."""
        mixed_input = "namespace: kube-system, pod=coredns-abc, invalid format here"
        
        result = builder.convert_action_to_tool_call(
            "kubectl.logs",
            mixed_input
        )
        
        assert result['server'] == 'kubectl'
        assert result['tool'] == 'logs'
        assert result['parameters']['namespace'] == 'kube-system'
        assert result['parameters']['pod'] == 'coredns-abc'
    
    def test_convert_action_empty_input_fallback(self, builder):
        """Test converting action with empty input."""
        result = builder.convert_action_to_tool_call(
            "test.action",
            ""
        )
        
        assert result['parameters']['input'] == ""


@pytest.mark.unit
class TestObservationFormatting:
    """Test MCP data observation formatting."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_format_empty_observation(self, builder):
        """Test formatting empty MCP data."""
        result = builder.format_observation({})
        
        assert result == "No data returned from the action."
    
    def test_format_none_observation(self, builder):
        """Test formatting None MCP data."""
        result = builder.format_observation(None)
        
        assert result == "No data returned from the action."
    
    def test_format_observation_with_results(self, builder):
        """Test formatting MCP data with results."""
        mcp_data = {
            "kubectl": [
                {
                    "tool": "get_pods",
                    "result": {
                        "pods": [
                            {"name": "pod1", "status": "Running"},
                            {"name": "pod2", "status": "Pending"}
                        ]
                    }
                }
            ]
        }
        
        result = builder.format_observation(mcp_data)
        
        assert "kubectl.get_pods:" in result
        assert "pod1" in result
        assert "Running" in result
        assert "pod2" in result
        assert "Pending" in result
    
    def test_format_observation_with_errors(self, builder):
        """Test formatting MCP data with errors."""
        mcp_data = {
            "kubectl": [
                {
                    "tool": "get_namespace",
                    "error": "Namespace 'nonexistent' not found"
                }
            ]
        }
        
        result = builder.format_observation(mcp_data)
        
        assert "kubectl.get_namespace error:" in result
        assert "Namespace 'nonexistent' not found" in result
    
    def test_format_observation_mixed_results_and_errors(self, builder):
        """Test formatting MCP data with both results and errors."""
        mcp_data = {
            "kubectl": [
                {
                    "tool": "get_pods",
                    "result": {"pods": ["pod1"]}
                },
                {
                    "tool": "get_services",
                    "error": "Permission denied"
                }
            ]
        }
        
        result = builder.format_observation(mcp_data)
        
        assert "kubectl.get_pods:" in result
        assert "kubectl.get_services error:" in result
        assert "Permission denied" in result
    
    def test_format_observation_legacy_format(self, builder):
        """Test formatting legacy MCP data format."""
        mcp_data = {
            "server1": {"some": "data", "status": "success"},
            "server2": {"error": "failed"}
        }
        
        result = builder.format_observation(mcp_data)
        
        assert "server1:" in result
        assert "server2:" in result
        assert "some" in result
        assert "failed" in result
    
    def test_format_observation_complex_nested_data(self, builder):
        """Test formatting complex nested data structures."""
        mcp_data = {
            "kubectl": [
                {
                    "tool": "describe_pod",
                    "result": {
                        "metadata": {
                            "name": "test-pod",
                            "labels": {"app": "test", "version": "v1"}
                        },
                        "spec": {
                            "containers": [
                                {"name": "app", "image": "nginx:1.20"}
                            ]
                        },
                        "status": {
                            "phase": "Running",
                            "conditions": [
                                {"type": "Ready", "status": "True"}
                            ]
                        }
                    }
                }
            ]
        }
        
        result = builder.format_observation(mcp_data)
        
        # Should format as JSON with proper indentation
        assert "kubectl.describe_pod:" in result
        assert '"name": "test-pod"' in result
        assert '"phase": "Running"' in result
        assert "nginx:1.20" in result


@pytest.mark.unit
class TestReActContinuationPrompts:
    """Test ReAct continuation prompt generation."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_get_react_continuation_general(self, builder):
        """Test general continuation prompt."""
        result = builder.get_react_continuation_prompt("general")
        
        assert len(result) == 2
        assert result[1] == "Thought:"
        assert "Choose ONE option" in result[0]
        assert "do NOT generate fake observations" in result[0]
    
    def test_get_react_continuation_data_collection(self, builder):
        """Test data collection continuation prompt."""
        result = builder.get_react_continuation_prompt("data_collection")
        
        assert len(result) == 2
        assert "Continue data collection" in result[0]
        assert "sufficient data" in result[0]
    
    def test_get_react_continuation_analysis(self, builder):
        """Test analysis continuation prompt."""
        result = builder.get_react_continuation_prompt("analysis")
        
        assert len(result) == 2
        assert "Continue investigating" in result[0]
        assert "complete analysis" in result[0]
    
    def test_get_react_continuation_unknown_context(self, builder):
        """Test continuation with unknown context defaults to general."""
        result = builder.get_react_continuation_prompt("unknown_context")
        
        # Should default to general prompt
        general_result = builder.get_react_continuation_prompt("general")
        assert result == general_result
    
    def test_get_react_error_continuation(self, builder):
        """Test error continuation prompt generation."""
        error_message = "Tool execution failed: Connection timeout"
        
        result = builder.get_react_error_continuation(error_message)
        
        assert len(result) == 2
        assert result[1] == "Thought:"
        assert "Error in reasoning" in result[0]
        assert error_message in result[0]
        assert "try a different approach" in result[0]


@pytest.mark.unit
class TestSectionExtraction:
    """Test ReAct section extraction helper methods."""
    
    @pytest.fixture
    def builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_extract_section_content_normal(self, builder):
        """Test normal section content extraction."""
        line = "Action: kubectl.get_pods"
        result = builder._extract_section_content(line, "Action: ")
        
        assert result == "kubectl.get_pods"
    
    def test_extract_section_content_empty_line(self, builder):
        """Test extraction from empty line."""
        result = builder._extract_section_content("", "Action: ")
        
        assert result == ""
    
    def test_extract_section_content_empty_prefix(self, builder):
        """Test extraction with empty prefix."""
        result = builder._extract_section_content("some content", "")
        
        assert result == ""
    
    def test_extract_section_content_line_shorter_than_prefix(self, builder):
        """Test extraction when line is shorter than prefix."""
        result = builder._extract_section_content("Act", "Action: ")
        
        assert result == ""
    
    def test_extract_section_content_exact_prefix_length(self, builder):
        """Test extraction when line exactly matches prefix."""
        result = builder._extract_section_content("Action:", "Action:")
        
        assert result == ""
    
    def test_is_section_header_thought_variations(self, builder):
        """Test thought section header detection."""
        found_sections = set()
        
        assert builder._is_section_header("Thought:", "thought", found_sections) is True
        assert builder._is_section_header("Thought", "thought", found_sections) is True
        assert builder._is_section_header("thinking:", "thought", found_sections) is False
    
    def test_is_section_header_duplicate_final_answer(self, builder):
        """Test that duplicate final answer is rejected."""
        found_sections = {"final_answer"}
        
        # Should reject duplicate final answer
        assert builder._is_section_header("Final Answer:", "final_answer", found_sections) is False
        
        # But allow other duplicates
        assert builder._is_section_header("Thought:", "thought", found_sections) is True
    
    def test_should_stop_parsing_conditions(self, builder):
        """Test various stop parsing conditions."""
        # Should stop on fake content markers
        assert builder._should_stop_parsing("[Based on the investigation") is True
        
        # Should stop on hallucinated observations (but not continuation prompts)
        assert builder._should_stop_parsing("Observation: The pod is running") is True
        assert builder._should_stop_parsing("Observation: Please specify what Action") is False
        assert builder._should_stop_parsing("Observation: Error in reasoning") is False
        
        # Should not stop on empty lines
        assert builder._should_stop_parsing("") is False
        assert builder._should_stop_parsing(None) is False
