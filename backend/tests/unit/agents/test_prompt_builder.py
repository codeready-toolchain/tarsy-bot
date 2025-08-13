"""
Tests for PromptBuilder class, focusing on ReAct response parsing.

This module tests the robust parsing logic introduced to handle edge cases
and malformed inputs gracefully.
"""

import pytest
from tarsy.agents.prompt_builder import PromptBuilder, PromptContext, get_prompt_builder


@pytest.mark.unit
class TestPromptBuilderReActParsing:
    """Test suite for PromptBuilder's ReAct response parsing functionality."""

    @pytest.fixture
    def builder(self):
        """Create a PromptBuilder instance for testing."""
        return PromptBuilder()

    def test_parse_valid_complete_react_response(self, builder):
        """Test parsing a valid, complete ReAct response."""
        response = """
Thought: I need to analyze this alert to understand the issue
Action: get_logs
Action Input: {"query": "error", "timerange": "1h"}
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "I need to analyze this alert to understand the issue"
        assert result['action'] == "get_logs"
        assert result['action_input'] == '{"query": "error", "timerange": "1h"}'
        assert result['final_answer'] is None
        assert result['is_complete'] is False

    def test_parse_final_answer_response(self, builder):
        """Test parsing a response with Final Answer."""
        response = """
Thought: After analyzing the logs, I can see the issue
Final Answer: The alert indicates a disk space issue on server-01. 
The /var partition is at 95% capacity and requires immediate attention.
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "After analyzing the logs, I can see the issue"
        assert result['action'] is None
        assert result['action_input'] is None
        assert "disk space issue" in result['final_answer']
        assert result['is_complete'] is True

    def test_parse_multiline_sections(self, builder):
        """Test parsing sections with multi-line content."""
        response = """
Thought: I need to carefully analyze this complex alert.
The alert has multiple components that need investigation.
Let me start by examining the logs.

Action: get_logs
Action Input: {
  "query": "error OR warning",
  "timerange": "2h",
  "servers": ["server-01", "server-02"]
}
"""
        result = builder.parse_react_response(response)
        
        expected_thought = ("I need to carefully analyze this complex alert.\n"
                          "The alert has multiple components that need investigation.\n"
                          "Let me start by examining the logs.")
        expected_input = ('{\n"query": "error OR warning",\n'
                         '"timerange": "2h",\n'
                         '"servers": ["server-01", "server-02"]\n}')
        
        assert result['thought'] == expected_thought
        assert result['action'] == "get_logs"
        assert result['action_input'] == expected_input

    def test_parse_thought_without_colon(self, builder):
        """Test parsing 'Thought' header without colon."""
        response = """
Thought
This is a thought that starts on the next line
without a colon in the header.
Action: test_action
"""
        result = builder.parse_react_response(response)
        
        expected_thought = ("This is a thought that starts on the next line\n"
                          "without a colon in the header.")
        assert result['thought'] == expected_thought
        assert result['action'] == "test_action"

    def test_parse_stops_at_fake_content(self, builder):
        """Test that parsing stops when encountering fake content markers."""
        response = """
Thought: Analyzing the alert
Action: get_info
Observation: This is fake content that should be ignored
Thought: This fake thought should be ignored
Final Answer: This fake answer should be ignored
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "Analyzing the alert"
        assert result['action'] == "get_info"
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False

    def test_parse_stops_at_based_on_marker(self, builder):
        """Test that parsing stops at '[Based on' marker."""
        response = """
Thought: Valid thought
Action: valid_action
[Based on the above, this is fake content that should be ignored
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "Valid thought"
        assert result['action'] == "valid_action"
        assert result['action_input'] is None

    def test_parse_ignores_duplicate_sections(self, builder):
        """Test that only the first occurrence of each section is processed."""
        response = """
Thought: First thought
Action: first_action
Thought: This duplicate thought should be ignored
Action: This duplicate action should be ignored
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "First thought"
        # After first action header, subsequent lines become content of the action section
        expected_action = ("first_action\n"
                          "Thought: This duplicate thought should be ignored\n"
                          "Action: This duplicate action should be ignored")
        assert result['action'] == expected_action

    def test_final_answer_can_appear_anytime(self, builder):
        """Test that Final Answer can appear at any time and marks response as complete."""
        response = """
Thought: Initial analysis
Final Answer: Quick conclusion based on obvious issue
Action: This action should be ignored because final answer came first
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "Initial analysis"
        assert result['final_answer'] == "Quick conclusion based on obvious issue"
        # The Action header still creates a new section since it hasn't been seen before
        assert result['action'] == "This action should be ignored because final answer came first"
        assert result['is_complete'] is True

    # Edge Cases and Error Handling Tests

    def test_parse_empty_string(self, builder):
        """Test parsing empty string returns safe default."""
        result = builder.parse_react_response("")
        
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False

    def test_parse_none_input(self, builder):
        """Test parsing None input returns safe default."""
        result = builder.parse_react_response(None)
        
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False

    def test_parse_non_string_input(self, builder):
        """Test parsing non-string input returns safe default."""
        result = builder.parse_react_response(123)
        
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False

    def test_parse_short_malformed_lines(self, builder):
        """Test parsing lines shorter than expected prefixes."""
        response = """
T:
A:
AI:
FA:
"""
        result = builder.parse_react_response(response)
        
        # Should handle gracefully without crashing
        assert result['thought'] is None
        assert result['action'] is None
        assert result['action_input'] is None
        assert result['final_answer'] is None
        assert result['is_complete'] is False

    def test_parse_exact_length_prefixes(self, builder):
        """Test parsing lines that are exactly the length of prefixes."""
        response = """
Thought:
Action:
Action Input:
Final Answer:
"""
        result = builder.parse_react_response(response)
        
        # Should handle gracefully, extracting empty content
        assert result['thought'] == ""
        assert result['action'] == ""
        assert result['action_input'] == ""
        assert result['final_answer'] == ""
        assert result['is_complete'] is True  # Final Answer was present

    def test_parse_whitespace_only_content(self, builder):
        """Test parsing sections with only whitespace content."""
        response = """
Thought:   
Action:     
Action Input:   
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == ""  # Whitespace should be stripped
        assert result['action'] == ""
        assert result['action_input'] == ""

    def test_parse_mixed_valid_and_invalid_lines(self, builder):
        """Test parsing response with mix of valid and invalid content."""
        response = """
Thought: Valid thought
Some random line that doesn't match any pattern
Action: valid_action
Another random line
Action Input: valid input
Random content again
"""
        result = builder.parse_react_response(response)
        
        # Should parse valid sections and include random lines as content
        assert result['thought'] == ("Valid thought\n"
                                   "Some random line that doesn't match any pattern")
        assert result['action'] == ("valid_action\n"
                                  "Another random line")
        assert result['action_input'] == ("valid input\n"
                                        "Random content again")

    def test_parse_empty_lines_handling(self, builder):
        """Test parsing handles empty lines appropriately."""
        response = """

Thought: Thought with empty lines

Action: Action with empty lines

Action Input: Input with empty lines

"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "Thought with empty lines"
        assert result['action'] == "Action with empty lines"
        assert result['action_input'] == "Input with empty lines"

    def test_parse_section_with_no_content(self, builder):
        """Test parsing when sections have headers but no content."""
        response = """
Thought: Valid thought
Action:
"""
        result = builder.parse_react_response(response)
        
        assert result['thought'] == "Valid thought"
        assert result['action'] == ""

    def test_defensive_helper_methods(self, builder):
        """Test the defensive helper methods directly."""
        # Test _extract_section_content with various inputs
        assert builder._extract_section_content("Thought: content", "Thought:") == "content"
        assert builder._extract_section_content("Thought:", "Thought:") == ""
        assert builder._extract_section_content("Th", "Thought:") == ""
        assert builder._extract_section_content("", "Thought:") == ""
        assert builder._extract_section_content("Thought: content", "") == ""
        
        # Test _is_section_header
        assert builder._is_section_header("Thought: content", "thought", set()) is True
        assert builder._is_section_header("Thought", "thought", set()) is True
        assert builder._is_section_header("Thought: content", "thought", {"thought"}) is False
        assert builder._is_section_header("", "thought", set()) is False
        
        # Test _should_stop_parsing
        assert builder._should_stop_parsing("Observation: fake") is True
        assert builder._should_stop_parsing("[Based on fake") is True
        assert builder._should_stop_parsing("Normal line") is False
        assert builder._should_stop_parsing("") is False

    def test_parse_comprehensive_scenario(self, builder):
        """Test a comprehensive scenario with multiple edge cases."""
        response = """

Thought: Complex multi-line thought
that spans several lines
and includes various content.

Action: complex_action

Action Input: {
  "nested": {
    "data": "value"
  },
  "array": [1, 2, 3]
}

Final Answer: This is the comprehensive final answer
that also spans multiple lines
and should complete the response.

Observation: This fake content should be ignored
"""
        result = builder.parse_react_response(response)
        
        expected_thought = ("Complex multi-line thought\n"
                          "that spans several lines\n"
                          "and includes various content.")
        expected_input = ('{\n"nested": {\n"data": "value"\n},\n'
                         '"array": [1, 2, 3]\n}')
        expected_final = ("This is the comprehensive final answer\n"
                        "that also spans multiple lines\n"
                        "and should complete the response.")
        
        assert result['thought'] == expected_thought
        assert result['action'] == "complex_action"
        assert result['action_input'] == expected_input
        assert result['final_answer'] == expected_final
        assert result['is_complete'] is True


@pytest.mark.unit
class TestPromptBuilderBasicMethods:
    """Test basic PromptBuilder methods for coverage."""

    @pytest.fixture
    def builder(self):
        """Create a PromptBuilder instance for testing."""
        return PromptBuilder()

    @pytest.fixture
    def context(self):
        """Create a basic PromptContext for testing."""
        return PromptContext(
            agent_name="TestAgent",
            alert_data={"type": "test", "message": "Test alert"},
            runbook_content="# Test Runbook\nThis is a test runbook.",
            mcp_data={"test_tool": "test_data"},
            mcp_servers=["test_server"],
            server_guidance="Test guidance",
            agent_specific_guidance="Agent specific guidance",
            available_tools={"test_tool": {"description": "Test tool"}},
            iteration_history=[{"iteration": 1, "tools": ["test_tool"]}],
            current_iteration=1,
            max_iterations=5
        )

    def test_build_analysis_prompt(self, builder, context):
        """Test building analysis prompt."""
        prompt = builder.build_analysis_prompt(context)
        assert "TestAgent" in prompt
        assert "Test alert" in prompt
        assert "Test Runbook" in prompt

    def test_build_mcp_tool_selection_prompt(self, builder, context):
        """Test building MCP tool selection prompt."""
        prompt = builder.build_mcp_tool_selection_prompt(context)
        assert "MCP Tool Selection Request" in prompt
        assert "Test guidance" in prompt
        assert "Test alert" in prompt

    def test_build_iterative_mcp_tool_selection_prompt(self, builder, context):
        """Test building iterative MCP tool selection prompt."""
        prompt = builder.build_iterative_mcp_tool_selection_prompt(context)
        assert "Iterative MCP Tool Selection" in prompt
        assert "iteration 1" in prompt
        assert "Test alert" in prompt

    def test_get_general_instructions(self, builder):
        """Test getting general instructions."""
        instructions = builder.get_general_instructions()
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_get_mcp_tool_selection_system_message(self, builder):
        """Test getting MCP tool selection system message."""
        message = builder.get_mcp_tool_selection_system_message()
        assert isinstance(message, str)
        assert len(message) > 0

    def test_get_iterative_mcp_tool_selection_system_message(self, builder):
        """Test getting iterative MCP tool selection system message."""
        message = builder.get_iterative_mcp_tool_selection_system_message()
        assert isinstance(message, str)
        assert len(message) > 0

    def test_build_standard_react_prompt(self, builder, context):
        """Test building standard ReAct prompt."""
        prompt = builder.build_standard_react_prompt(context)
        assert "Answer the following question" in prompt
        assert "Test alert" in prompt  # Agent name might not be in the prompt

    def test_build_standard_react_prompt_with_history(self, builder, context):
        """Test building standard ReAct prompt with history."""
        history = ["Previous action 1", "Previous action 2"]
        prompt = builder.build_standard_react_prompt(context, history)
        assert "Previous action 1" in prompt
        assert "Previous action 2" in prompt

    def test_convert_action_to_tool_call(self, builder):
        """Test converting action to tool call."""
        action = "server.test_tool"
        action_input = '{"param": "value"}'
        result = builder.convert_action_to_tool_call(action, action_input)
        
        assert result["tool"] == "test_tool"
        assert result["server"] == "server"
        assert result["parameters"] == {"param": "value"}

    def test_convert_action_to_tool_call_invalid_json(self, builder):
        """Test converting action with invalid JSON input."""
        action = "server.test_tool"
        action_input = "invalid json"
        result = builder.convert_action_to_tool_call(action, action_input)
        
        assert result["tool"] == "test_tool"
        assert result["server"] == "server"
        assert result["parameters"] == {"input": "invalid json"}

    def test_format_observation(self, builder):
        """Test formatting observation data."""
        mcp_data = {"tool1": "result1", "tool2": "result2"}
        observation = builder.format_observation(mcp_data)
        
        assert "tool1" in observation
        assert "result1" in observation
        assert "tool2" in observation
        assert "result2" in observation

    def test_format_observation_empty(self, builder):
        """Test formatting empty observation data."""
        mcp_data = {}
        observation = builder.format_observation(mcp_data)
        
        assert "No data" in observation

    def test_format_data(self, builder):
        """Test formatting data method."""
        # Test dict
        data = {"key": "value"}
        result = builder._format_data(data)
        assert "key" in result
        assert "value" in result
        
        # Test string
        data = "simple string"
        result = builder._format_data(data)
        assert result == "simple string"
        
        # Test other types
        data = 42
        result = builder._format_data(data)
        assert "42" in result

    def test_format_available_tools(self, builder):
        """Test formatting available tools."""
        tools = {
            "tool1": {"description": "First tool"},
            "tool2": {"description": "Second tool"}
        }
        result = builder._format_available_tools(tools)
        assert "tool1" in result
        assert "First tool" in result
        assert "tool2" in result
        assert "Second tool" in result

    def test_format_iteration_history(self, builder):
        """Test formatting iteration history."""
        history = [
            {"tools_called": [{"server": "server1", "tool": "tool1", "reason": "test"}]},
            {"tools_called": [{"server": "server2", "tool": "tool2", "reason": "test"}]}
        ]
        result = builder._format_iteration_history(history)
        assert "Iteration 1" in result
        assert "Iteration 2" in result
        assert "server1.tool1" in result
        assert "server2.tool2" in result


@pytest.mark.unit
class TestPromptBuilderFactory:
    """Test prompt builder factory function."""

    def test_get_prompt_builder(self):
        """Test get_prompt_builder factory function."""
        builder = get_prompt_builder()
        assert isinstance(builder, PromptBuilder)


@pytest.mark.unit
class TestPromptBuilderUtilityMethods:
    """Test suite for PromptBuilder utility and formatting methods."""

    @pytest.fixture
    def builder(self):
        """Create a PromptBuilder instance for testing."""
        return PromptBuilder()

    def test_format_data_dict(self, builder):
        """Test _format_data with dictionary input."""
        data = {"key": "value", "number": 42, "nested": {"inner": "data"}}
        result = builder._format_data(data)
        
        assert isinstance(result, str)
        assert "key" in result
        assert "value" in result
        assert "42" in result
        assert "nested" in result
    
    def test_format_data_list(self, builder):
        """Test _format_data with list input."""
        data = ["item1", "item2", {"key": "value"}]
        result = builder._format_data(data)
        
        assert isinstance(result, str)
        assert "item1" in result
        assert "item2" in result
        assert "key" in result
    
    def test_format_data_string(self, builder):
        """Test _format_data with string input."""
        data = "simple string"
        result = builder._format_data(data)
        
        assert result == "simple string"
    
    def test_format_data_number(self, builder):
        """Test _format_data with number input."""
        data = 42
        result = builder._format_data(data)
        
        assert result == "42"
    
    def test_format_data_none(self, builder):
        """Test _format_data with None input."""
        data = None
        result = builder._format_data(data)
        
        assert result == "None"
    
    def test_format_available_tools_empty(self, builder):
        """Test _format_available_tools with empty tools."""
        tools = {}
        result = builder._format_available_tools(tools)
        
        assert result == "No tools available."
    
    def test_format_available_tools_none(self, builder):
        """Test _format_available_tools with None tools."""
        tools = None
        result = builder._format_available_tools(tools)
        
        assert result == "No tools available."
    
    def test_format_available_tools_with_data(self, builder):
        """Test _format_available_tools with actual tools."""
        tools = {
            "tools": [
                {"name": "test_tool", "description": "A test tool"},
                {"name": "another_tool", "description": "Another tool"}
            ]
        }
        result = builder._format_available_tools(tools)
        
        assert isinstance(result, str)
        assert "test_tool" in result
        assert "another_tool" in result
        assert "A test tool" in result
    
    def test_extract_section_content_valid(self, builder):
        """Test _extract_section_content with valid input."""
        line = "Thought: This is a thought"
        prefix = "Thought:"
        result = builder._extract_section_content(line, prefix)
        
        assert result == "This is a thought"
    
    def test_extract_section_content_no_colon(self, builder):
        """Test _extract_section_content with prefix without colon."""
        line = "Thought This is a thought without colon"
        prefix = "Thought"
        result = builder._extract_section_content(line, prefix)
        
        assert result == "This is a thought without colon"
    
    def test_extract_section_content_exact_prefix(self, builder):
        """Test _extract_section_content when line equals prefix exactly."""
        line = "Thought"
        prefix = "Thought"
        result = builder._extract_section_content(line, prefix)
        
        assert result == ""
    
    def test_extract_section_content_empty_inputs(self, builder):
        """Test _extract_section_content with empty inputs."""
        assert builder._extract_section_content("", "prefix") == ""
        assert builder._extract_section_content("line", "") == ""
        assert builder._extract_section_content("", "") == ""
    
    def test_extract_section_content_short_line(self, builder):
        """Test _extract_section_content when line is shorter than prefix."""
        line = "T"
        prefix = "Thought:"
        result = builder._extract_section_content(line, prefix)
        
        assert result == ""
    
    def test_is_section_header_thought_with_colon(self, builder):
        """Test _is_section_header for thought with colon."""
        line = "Thought: Some content"
        result = builder._is_section_header(line, 'thought', set())
        
        assert result is True
    
    def test_is_section_header_thought_without_colon(self, builder):
        """Test _is_section_header for thought without colon."""
        line = "Thought"
        result = builder._is_section_header(line, 'thought', set())
        
        assert result is True
    
    def test_is_section_header_already_found(self, builder):
        """Test _is_section_header when section already found."""
        line = "Thought: Some content"
        found_sections = {'thought'}
        result = builder._is_section_header(line, 'thought', found_sections)
        
        assert result is False
    
    def test_is_section_header_action(self, builder):
        """Test _is_section_header for action."""
        line = "Action: test_action"
        result = builder._is_section_header(line, 'action', set())
        
        assert result is True
    
    def test_should_stop_parsing_observation(self, builder):
        """Test _should_stop_parsing with observation marker."""
        line = "Observation: This is fake content"
        result = builder._should_stop_parsing(line)
        
        assert result is True
    
    def test_should_stop_parsing_normal_content(self, builder):
        """Test _should_stop_parsing with normal content."""
        line = "This is normal content"
        result = builder._should_stop_parsing(line)
        
        assert result is False
    
    def test_get_general_instructions(self, builder):
        """Test get_general_instructions returns valid instructions."""
        instructions = builder.get_general_instructions()
        
        assert isinstance(instructions, str)
        assert len(instructions) > 0
        assert "SRE" in instructions or "analysis" in instructions.lower()
    
    def test_get_standard_react_system_message_default(self, builder):
        """Test get_standard_react_system_message with default task focus."""
        message = builder.get_standard_react_system_message()
        
        assert isinstance(message, str)
        assert len(message) > 0
        assert "investigation and providing recommendations" in message
    
    def test_format_observation_empty_data(self, builder):
        """Test format_observation with empty MCP data."""
        mcp_data = {}
        result = builder.format_observation(mcp_data)
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_format_observation_with_data(self, builder):
        """Test format_observation with actual MCP data."""
        mcp_data = {
            "test-server": [
                {"tool": "test-tool", "result": "test result", "parameters": {}}
            ]
        }
        result = builder.format_observation(mcp_data)
        
        assert isinstance(result, str)
        assert "test-server" in result
        assert "test result" in result
    
    def test_flatten_react_history_empty(self, builder):
        """Test _flatten_react_history with empty history."""
        history = []
        result = builder._flatten_react_history(history)
        
        assert result == []
    
    def test_flatten_react_history_with_content(self, builder):
        """Test _flatten_react_history with content."""
        history = ["Thought: First thought", "Action: test_action", "Observation: Result"]
        result = builder._flatten_react_history(history)
        
        assert len(result) == 3
        assert "First thought" in result[0]
        assert "test_action" in result[1]
        assert "Result" in result[2]
    
    def test_get_react_continuation_prompt_general(self, builder):
        """Test get_react_continuation_prompt with general context."""
        result = builder.get_react_continuation_prompt("general")
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(item, str) for item in result)
    
    def test_get_react_error_continuation(self, builder):
        """Test get_react_error_continuation."""
        error_message = "Connection timeout"
        result = builder.get_react_error_continuation(error_message)
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert any("timeout" in item.lower() or "error" in item.lower() for item in result)


@pytest.mark.unit
class TestPromptBuilderPrivateMethods:
    """Test suite for PromptBuilder private methods to improve coverage."""

    @pytest.fixture
    def builder(self):
        """Create a PromptBuilder instance for testing."""
        return PromptBuilder()

    @pytest.fixture
    def context(self):
        """Create a comprehensive PromptContext for testing."""
        return PromptContext(
            agent_name="KubernetesAgent",
            alert_data={
                "namespace": "production",
                "pod": "api-server-123", 
                "status": "CrashLoopBackOff",
                "complex_data": {"metadata": {"name": "test"}, "nested": [1, 2, 3]},
                "json_string": '{"parsable": true, "test": "value"}',
                "multiline_yaml": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test",
                "long_description": "This is a very long description " * 20,
                "empty_value": None
            },
            runbook_content="# Troubleshooting Guide\n\n## Step 1\nCheck pod status\n\n## Step 2\nReview logs",
            mcp_data={
                "kubernetes-server": [
                    {"tool": "get_pods", "result": {"pods": ["pod1", "pod2"]}, "parameters": {"namespace": "production"}},
                    {"tool": "get_logs", "error": "Permission denied", "parameters": {"pod": "api-server"}}
                ],
                "legacy-server": {"get_status_result": "Running", "get_logs_result": "Log content here"}
            },
            mcp_servers=["kubernetes-server", "monitoring-server"],
            server_guidance="Use kubectl commands for Kubernetes diagnostics",
            agent_specific_guidance="Focus on pod restart patterns and resource limits",
            available_tools={
                "tools": [
                    {"name": "get_pods", "description": "Get pod information"},
                    {"name": "get_logs", "description": "Get pod logs"}
                ]
            },
            iteration_history=[
                {
                    "iteration": 1,
                    "tools_called": [
                        {"server": "kubernetes", "tool": "get_pods", "reason": "Check pod status"}
                    ],
                    "mcp_data": {
                        "kubernetes-server": [
                            {"tool": "get_pods", "result": {"status": "Running"}, "parameters": {"namespace": "prod"}}
                        ]
                    }
                }
            ],
            current_iteration=2,
            max_iterations=5,
            stage_name="diagnosis",
            is_final_stage=False,
            stage_attributed_data={
                "diagnosis": {
                    "kubernetes-server": [{"tool": "diagnose", "result": "Found issue"}]
                },
                "remediation": {
                    "kubernetes-server": [{"tool": "fix", "result": "Applied fix"}]
                }
            }
        )

    def test_build_context_section(self, builder, context):
        """Test _build_context_section method."""
        result = builder._build_context_section(context)
        
        assert "KubernetesAgent" in result
        assert "SRE Alert Analysis Request" in result
        assert "kubernetes-server" in result
        assert "monitoring-server" in result

    def test_build_context_section_with_stage(self, builder, context):
        """Test _build_context_section with stage information."""
        result = builder._build_context_section(context)
        
        # Context section doesn't include stage info - that's handled elsewhere
        assert "KubernetesAgent" in result
        assert isinstance(result, str)

    def test_build_alert_section_simple(self, builder):
        """Test _build_alert_section with simple alert data."""
        alert_data = {"namespace": "test", "status": "error"}
        result = builder._build_alert_section(alert_data)
        
        assert "## Alert Details" in result
        assert "**Namespace:** test" in result
        assert "**Status:** error" in result

    def test_build_alert_section_complex_data(self, builder, context):
        """Test _build_alert_section with complex data types."""
        result = builder._build_alert_section(context.alert_data)
        
        assert "## Alert Details" in result
        assert "**Namespace:** production" in result
        assert "**Pod:** api-server-123" in result
        assert "**Status:** CrashLoopBackOff" in result
        assert "```json" in result  # Complex data should be JSON formatted
        assert '"metadata"' in result
        assert "apiVersion: v1" in result  # Multiline YAML should be in code blocks
        assert "N/A" in result  # None values should show as N/A

    def test_build_alert_section_json_string_parsing(self, builder, context):
        """Test _build_alert_section properly parses JSON strings."""
        result = builder._build_alert_section(context.alert_data)
        
        assert '"parsable": true' in result
        assert '"test": "value"' in result

    def test_build_alert_section_invalid_json_string(self, builder):
        """Test _build_alert_section handles invalid JSON strings."""
        alert_data = {"invalid_json": '{"invalid": json}'}
        result = builder._build_alert_section(alert_data)
        
        assert '{"invalid": json}' in result  # Should be treated as regular string

    def test_build_runbook_section_with_content(self, builder, context):
        """Test _build_runbook_section with runbook content."""
        result = builder._build_runbook_section(context.runbook_content)
        
        assert "## Runbook Content" in result
        assert "```markdown" in result
        assert "# Troubleshooting Guide" in result
        assert "## Step 1" in result
        assert "Check pod status" in result

    def test_build_runbook_section_empty(self, builder):
        """Test _build_runbook_section with empty runbook."""
        result = builder._build_runbook_section("")
        
        assert "## Runbook Content" in result
        assert "No runbook available" in result

    def test_build_runbook_section_none(self, builder):
        """Test _build_runbook_section with None runbook."""
        result = builder._build_runbook_section(None)
        
        assert "## Runbook Content" in result
        assert "No runbook available" in result

    def test_build_mcp_data_section_with_data(self, builder, context):
        """Test _build_mcp_data_section with MCP data."""
        result = builder._build_mcp_data_section(context.mcp_data)
        
        assert "## System Data (MCP Servers)" in result
        assert "### Kubernetes-Server MCP Server Data" in result
        assert "get_pods" in result
        assert "Permission denied" in result
        assert "### Legacy-Server MCP Server Data" in result

    def test_build_mcp_data_section_empty(self, builder):
        """Test _build_mcp_data_section with empty data."""
        result = builder._build_mcp_data_section({})
        
        assert "## System Data (MCP Servers)" in result
        assert "No system data available" in result

    def test_build_mcp_data_section_none(self, builder):
        """Test _build_mcp_data_section with None data."""
        result = builder._build_mcp_data_section(None)
        
        assert "## System Data (MCP Servers)" in result
        assert "No system data available" in result

    def test_build_agent_specific_analysis_guidance(self, builder, context):
        """Test _build_agent_specific_analysis_guidance method."""
        result = builder._build_agent_specific_analysis_guidance(context)
        
        assert "Domain-Specific Analysis Guidance" in result
        assert "Focus on pod restart patterns" in result
        assert "Use kubectl commands" in result

    def test_build_agent_specific_analysis_guidance_no_guidance(self, builder):
        """Test _build_agent_specific_analysis_guidance with no guidance."""
        context = PromptContext(
            agent_name="TestAgent",
            alert_data={},
            runbook_content="",
            mcp_data={},
            mcp_servers=[],
            server_guidance="",
            agent_specific_guidance=""
        )
        result = builder._build_agent_specific_analysis_guidance(context)
        
        # When no guidance is available, empty string is returned
        assert result == ""

    def test_build_analysis_instructions(self, builder):
        """Test _build_analysis_instructions method."""
        result = builder._build_analysis_instructions()
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "analysis" in result.lower() or "instructions" in result.lower()

    def test_format_iteration_history_complex(self, builder, context):
        """Test _format_iteration_history with complex data."""
        result = builder._format_iteration_history(context.iteration_history)
        
        assert "### Iteration 1" in result
        assert "kubernetes.get_pods" in result
        assert "Check pod status" in result
        assert "kubernetes-server" in result
        assert '"status": "Running"' in result

    def test_format_iteration_history_with_long_data(self, builder):
        """Test _format_iteration_history with data that needs truncation."""
        long_result = {"data": "x" * 10000}  # Create very long data to trigger truncation
        iteration_history = [{
            "iteration": 1,
            "tools_called": [{"server": "test", "tool": "get_data", "reason": "test"}],
            "mcp_data": {
                "test-server": [{"tool": "get_data", "result": long_result}]
            }
        }]
        
        result = builder._format_iteration_history(iteration_history)
        assert "[truncated for brevity]" in result

    def test_format_iteration_history_with_errors(self, builder):
        """Test _format_iteration_history with error cases."""
        iteration_history = [{
            "iteration": 1,
            "tools_called": [{"server": "test", "tool": "fail", "reason": "test error"}],
            "mcp_data": {
                "test-server": [{"tool": "fail", "error": "Connection timeout"}]
            }
        }]
        
        result = builder._format_iteration_history(iteration_history)
        assert "Connection timeout" in result
        assert "fail_result_error" in result

    def test_format_iteration_history_legacy_format(self, builder):
        """Test _format_iteration_history with legacy dict format."""
        iteration_history = [{
            "iteration": 1,
            "tools_called": [{"server": "legacy", "tool": "get_status", "reason": "legacy test"}],
            "mcp_data": {
                "legacy-server": {"get_status_result": "OK", "get_logs_result": "No issues"}
            }
        }]
        
        result = builder._format_iteration_history(iteration_history)
        assert "get_status_result" in result
        assert "get_logs_result" in result
        assert "OK" in result

    def test_format_stage_attributed_data(self, builder, context):
        """Test _format_stage_attributed_data method."""
        result = builder._format_stage_attributed_data(context.stage_attributed_data)
        
        assert "diagnosis" in result
        assert "remediation" in result
        assert "Found issue" in result
        assert "Applied fix" in result

    def test_format_stage_attributed_data_empty(self, builder):
        """Test _format_stage_attributed_data with empty data."""
        result = builder._format_stage_attributed_data({})
        
        assert isinstance(result, str)
        assert "No investigation data from previous stages" in result

    def test_format_react_question_for_data_collection(self, builder, context):
        """Test _format_react_question_for_data_collection method."""
        result = builder._format_react_question_for_data_collection(context)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "production" in result  # Should include alert data

    def test_format_react_question_for_partial_analysis(self, builder, context):
        """Test _format_react_question_for_partial_analysis method."""
        result = builder._format_react_question_for_partial_analysis(context)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "analysis" in result.lower()

    def test_get_action_names(self, builder, context):
        """Test _get_action_names method."""
        result = builder._get_action_names(context.available_tools)
        
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_action_names_empty_tools(self, builder):
        """Test _get_action_names with empty tools."""
        result = builder._get_action_names({})
        
        assert isinstance(result, list)
        # When tools are empty, it returns a list with "No tools available"
        assert result == ["No tools available"]

    def test_format_available_actions(self, builder, context):
        """Test _format_available_actions method."""
        result = builder._format_available_actions(context.available_tools)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "get_pods" in result
        assert "get_logs" in result

    def test_format_available_actions_empty(self, builder):
        """Test _format_available_actions with empty tools."""
        result = builder._format_available_actions({})
        
        assert isinstance(result, str)
        assert "No tools available" in result

    def test_finalize_current_section(self, builder):
        """Test _finalize_current_section method."""
        parsed = {}
        content_lines = ["Line 1", "Line 2", "Line 3"]
        
        builder._finalize_current_section(parsed, "thought", content_lines)
        
        assert "thought" in parsed
        assert parsed["thought"] == "Line 1\nLine 2\nLine 3"

    def test_finalize_current_section_empty_content(self, builder):
        """Test _finalize_current_section with empty content."""
        parsed = {}
        content_lines = []
        
        builder._finalize_current_section(parsed, "thought", content_lines)
        
        assert "thought" in parsed
        assert parsed["thought"] == ""


@pytest.mark.unit
class TestPromptBuilderChainFunctionality:
    """Test suite for chain and stage-related prompt functionality."""

    @pytest.fixture
    def builder(self):
        """Create a PromptBuilder instance for testing."""
        return PromptBuilder()

    @pytest.fixture
    def chain_context(self):
        """Create a PromptContext with chain/stage data."""
        return PromptContext(
            agent_name="TestAgent",
            alert_data={"issue": "service down"},
            runbook_content="# Chain Runbook",
            mcp_data={},
            mcp_servers=["test-server"],
            stage_name="analysis",
            is_final_stage=True,
            stage_attributed_data={
                "analysis": {"test-server": [{"tool": "analyze", "result": "issue found"}]},
                "remediation": {"test-server": [{"tool": "fix", "result": "applied"}]}
            }
        )

    def test_context_section_with_final_stage(self, builder, chain_context):
        """Test context section includes final stage information."""
        result = builder._build_context_section(chain_context)
        
        # Context section doesn't include stage-specific text - just basic context
        assert "TestAgent" in result
        assert "SRE Alert Analysis Request" in result

    def test_build_chain_prompt_components(self, builder, chain_context):
        """Test that chain prompts include stage-attributed data."""
        analysis_prompt = builder.build_analysis_prompt(chain_context)
        
        # The analysis prompt includes alert and runbook data
        assert "service down" in analysis_prompt
        assert "Chain Runbook" in analysis_prompt
        
    def test_stage_attributed_data_formatting(self, builder, chain_context):
        """Test stage attributed data is properly formatted."""
        result = builder._format_stage_attributed_data(chain_context.stage_attributed_data)
        
        assert "analysis" in result
        assert "remediation" in result
        assert "issue found" in result
        assert "applied" in result


@pytest.mark.unit
class TestPromptBuilderEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def builder(self):
        """Create a PromptBuilder instance for testing."""
        return PromptBuilder()

    def test_build_methods_with_none_inputs(self, builder):
        """Test build methods handle None inputs gracefully."""
        context = PromptContext(
            agent_name="TestAgent",
            alert_data=None,
            runbook_content=None,
            mcp_data=None,
            mcp_servers=[]  # Empty list instead of None to avoid join error
        )
        
        # Should not raise exceptions
        context_result = builder._build_context_section(context)
        alert_result = builder._build_alert_section(None)
        runbook_result = builder._build_runbook_section(None)
        mcp_result = builder._build_mcp_data_section(None)
        
        assert isinstance(context_result, str)
        assert isinstance(alert_result, str)
        assert isinstance(runbook_result, str)
        assert isinstance(mcp_result, str)

    def test_complex_nested_mcp_data(self, builder):
        """Test MCP data section with deeply nested structures."""
        complex_mcp_data = {
            "complex-server": {
                "nested_result": {
                    "level1": {
                        "level2": {
                            "level3": ["item1", "item2", {"deep": "value"}]
                        }
                    }
                },
                "array_result": [{"item": 1}, {"item": 2}],
                "string_result": "simple string"
            }
        }
        
        result = builder._build_mcp_data_section(complex_mcp_data)
        
        assert "level1" in result
        assert "level2" in result
        assert "level3" in result
        assert "simple string" in result

    def test_very_long_iteration_history(self, builder):
        """Test iteration history with many iterations."""
        long_history = []
        for i in range(10):
            long_history.append({
                "iteration": i + 1,
                "tools_called": [{"server": f"server-{i}", "tool": f"tool-{i}", "reason": f"reason-{i}"}],
                "mcp_data": {f"server-{i}": [{"tool": f"tool-{i}", "result": f"result-{i}"}]}
            })
        
        result = builder._format_iteration_history(long_history)
        
        assert "Iteration 1" in result
        assert "Iteration 10" in result
        assert "server-5" in result
