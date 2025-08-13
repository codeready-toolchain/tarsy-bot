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
