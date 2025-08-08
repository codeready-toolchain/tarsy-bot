"""
Tests for PromptBuilder class, focusing on ReAct response parsing.

This module tests the robust parsing logic introduced to handle edge cases
and malformed inputs gracefully.
"""

import pytest
from tarsy.agents.prompt_builder import PromptBuilder


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
