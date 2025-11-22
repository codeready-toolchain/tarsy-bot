"""
Comprehensive Test Matrix for Mid-Line Action Detection

This file provides a clear, tabular view of all test cases for the parser's
3-tier detection system. Each test explicitly shows:
1. Input format
2. Expected detection
3. Expected output
4. Reasoning

NO ASSUMPTIONS about LLM behavior - just explicit test coverage.
"""

import pytest
from tarsy.agents.parsers.react_parser import ReActParser


@pytest.mark.unit
class TestParserDetectionMatrix:
    """
    DETECTION MATRIX: Mid-Line Action Detection
    
    | Case # | Input Pattern                    | Detect? | Result      | Reason                |
    |--------|----------------------------------|---------|-------------|-----------------------|
    | V1     | "text.Action: tool"              | YES     | has_action  | Period + Action       |
    | V2     | "text!Action: tool"              | YES     | has_action  | Exclamation + Action  |
    | V3     | "text?Action: tool"              | YES     | has_action  | Question + Action     |
    | V4     | "text. Action: tool"             | YES     | has_action  | Period + space        |
    | V5     | "text.`Action: tool"             | YES     | has_action  | Period + backtick     |
    | V6     | "text.**Action: tool"            | YES     | has_action  | Period + markdown     |
    | V7     | "a. b. c.Action: tool"           | YES     | has_action  | Multiple sentences    |
    |--------|----------------------------------|---------|-------------|-----------------------|
    | I1     | "text action: tool"              | NO      | malformed   | Lowercase             |
    | I2     | "text Action: tool"              | NO      | malformed   | No sentence boundary  |
    | I3     | "The Action: concept"            | NO      | malformed   | Narrative (no punct)  |
    |--------|----------------------------------|---------|-------------|-----------------------|
    | P1     | "Final Answer: X.Action: Y"      | NO      | final_answer| Final Answer priority |
    |--------|----------------------------------|---------|-------------|-----------------------|
    | R1     | "Thought:\nAction: tool"         | YES     | has_action  | Standard format       |
    | R2     | "\nAction: tool\nAction Input:"  | YES     | has_action  | Line-start detection  |
    """
    
    # ========================================================================
    # CATEGORY V: VALID - Should Detect Action
    # ========================================================================
    
    def test_V1_period_plus_action(self):
        """
        V1: Period immediately before Action:
        
        INPUT:    "namespace.Action: kubernetes-server.resources_get"
        DETECT:   YES (Tier 3: period detected)
        RESULT:   has_action=True
        ACTION:   "kubernetes-server.resources_get"
        """
        response = """Thought:
I will check the namespace.Action: kubernetes-server.resources_get
Action Input:
apiVersion: v1
kind: Namespace
name: test
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect mid-line Action after period"
        assert parsed.is_malformed is False
        assert parsed.action == "kubernetes-server.resources_get"
        assert parsed.tool_call.server == "kubernetes-server"
        assert parsed.tool_call.tool == "resources_get"
    
    def test_V2_exclamation_plus_action(self):
        """
        V2: Exclamation mark before Action:
        
        INPUT:    "This is critical!Action: kubectl.emergency_stop"
        DETECT:   YES (Tier 3: exclamation detected)
        RESULT:   has_action=True
        ACTION:   "kubectl.emergency_stop"
        """
        response = """Thought: This is critical!Action: kubectl.emergency_stop
Action Input: namespace: prod
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect mid-line Action after exclamation"
        assert parsed.action == "kubectl.emergency_stop"
        assert parsed.tool_call.server == "kubectl"
        assert parsed.tool_call.tool == "emergency_stop"
    
    def test_V3_question_plus_action(self):
        """
        V3: Question mark before Action:
        
        INPUT:    "What should I do?Action: kubectl.get_status"
        DETECT:   YES (Tier 3: question mark detected)
        RESULT:   has_action=True
        ACTION:   "kubectl.get_status"
        """
        response = """Thought: What should I check first?Action: kubectl.get_status
Action Input: namespace: default
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect mid-line Action after question mark"
        assert parsed.action == "kubectl.get_status"
    
    def test_V4_period_space_plus_action(self):
        """
        V4: Period + space before Action:
        
        INPUT:    "I will proceed. Action: kubectl.do_something"
        DETECT:   YES (Tier 3: period + space pattern)
        RESULT:   has_action=True
        ACTION:   "kubectl.do_something"
        """
        response = """Thought: I will proceed. Action: kubectl.do_something
Action Input: param: value
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect Action after period+space"
        assert parsed.action == "kubectl.do_something"
    
    def test_V5_period_backtick_plus_action(self):
        """
        V5: Period + backtick before Action: (common with markdown inline code)
        
        INPUT:    "Check `namespace`.`Action: kubectl.check"
        DETECT:   YES (Tier 3: period + backtick pattern)
        RESULT:   has_action=True
        ACTION:   "kubectl.check"
        """
        response = """Thought: Check the `namespace`.`Action: kubectl.check
Action Input: name: test
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect Action after period+backtick"
        assert parsed.action == "kubectl.check"
    
    def test_V6_period_markdown_plus_action(self):
        """
        V6: Period + markdown emphasis before Action:
        
        INPUT:    "namespace.**Action: kubectl.check"
        DETECT:   YES (Tier 3: period + asterisks pattern)
        RESULT:   has_action=True
        ACTION:   "kubectl.check"
        """
        response = """Thought: **Important**: Check namespace.**Action: kubectl.check
Action Input: critical: true
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect Action after period+markdown"
        assert parsed.action == "kubectl.check"
    
    def test_V7_multiple_sentences_plus_action(self):
        """
        V7: Multiple sentences before Action:
        
        INPUT:    "Step 1. Step 2. Step 3.Action: kubectl.execute"
        DETECT:   YES (Tier 3: last period triggers detection)
        RESULT:   has_action=True
        ACTION:   "kubectl.execute"
        """
        response = """Thought: First step. Second step. Third step.Action: kubectl.execute
Action Input: command: run
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should detect Action after multiple periods"
        assert parsed.action == "kubectl.execute"
    
    # ========================================================================
    # CATEGORY I: INVALID - Should NOT Detect Action (Malformed)
    # ========================================================================
    
    def test_I1_lowercase_action(self):
        """
        I1: Lowercase "action:" should NOT trigger detection
        
        INPUT:    "take action: check logs"
        DETECT:   NO (case-sensitive matching)
        RESULT:   is_malformed=True
        REASON:   Lowercase 'action:' is narrative text, not a command
        """
        response = """Thought: I need to take action: check the logs first.

This is just narrative text.
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.is_malformed is True, "Lowercase 'action:' should NOT be detected"
        assert parsed.has_action is False
    
    def test_I2_no_sentence_boundary(self):
        """
        I2: "Action:" without sentence boundary should NOT trigger
        
        INPUT:    "The action: we should take"
        DETECT:   NO (no .!? before Action:)
        RESULT:   is_malformed=True
        REASON:   "action:" is part of narrative, not preceded by sentence end
        """
        response = """Thought: The action: we should take is to investigate.

Let's think about this carefully.
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.is_malformed is True, "Action without sentence boundary should NOT be detected"
        assert parsed.has_action is False
    
    def test_I3_narrative_mention(self):
        """
        I3: Narrative mention of "Action:" without proper boundary
        
        INPUT:    "Think about what Action: means"
        DETECT:   NO (word boundary, no punctuation)
        RESULT:   is_malformed=True
        REASON:   This is discussion about actions, not an action command
        """
        response = """Thought: Let's think about what Action: means here.

We need to handle this carefully.
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.is_malformed is True, "Narrative Action mention should NOT be detected"
        assert parsed.has_action is False
    
    # ========================================================================
    # CATEGORY P: PRIORITY - Section Priority Rules
    # ========================================================================
    
    def test_P1_final_answer_priority(self):
        """
        P1: Final Answer: takes priority over any Action: after it
        
        INPUT:    "Final Answer: Analysis done.Action: should-ignore"
        DETECT:   NO (Tier 2: Final Answer stops Action detection)
        RESULT:   is_final_answer=True, has_action=False
        REASON:   Once Final Answer detected, parsing should stop or ignore actions
        """
        response = """Thought: I have sufficient information.

Final Answer: The namespace is stuck due to finalizers.Action: this-should-not-parse
Action Input: ignored: true
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.is_final_answer is True, "Should detect Final Answer"
        assert parsed.has_action is False, "Should NOT detect Action after Final Answer"
        assert "finalizers" in parsed.final_answer
    
    # ========================================================================
    # CATEGORY R: REGRESSION - Standard Format Must Still Work
    # ========================================================================
    
    def test_R1_standard_multiline_format(self):
        """
        R1: Standard format with newlines should work (Tier 1)
        
        INPUT:    "Thought:\\nAction: tool\\nAction Input:"
        DETECT:   YES (Tier 1: line-start detection)
        RESULT:   has_action=True
        REASON:   This is the standard expected format, must always work
        """
        response = """Thought: I need to check the namespace.

Action: kubernetes-server.resources_get
Action Input: apiVersion: v1
kind: Namespace
name: test
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Standard format must work"
        assert parsed.action == "kubernetes-server.resources_get"
        assert parsed.tool_call.parameters["kind"] == "Namespace"
    
    def test_R2_action_at_line_start(self):
        """
        R2: Action: at line start with no Thought should work (Tier 1)
        
        INPUT:    "\\nAction: tool\\nAction Input:"
        DETECT:   YES (Tier 1: line-start detection, thought optional)
        RESULT:   has_action=True, thought=None
        REASON:   LLMs sometimes omit Thought, Action at line start is valid
        """
        response = """Action: kubectl.get_pods
Action Input: namespace: default
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Action at line start must work"
        assert parsed.action == "kubectl.get_pods"
        assert parsed.thought is None  # No thought provided
    
    # ========================================================================
    # CATEGORY E: EDGE CASES - Complex/Unusual Patterns
    # ========================================================================
    
    def test_E1_exact_gemini_failure(self):
        """
        E1: Exact real-world failure case from session f852cc9c-2276-4f35-a179-ebf622b0efd3
        
        INPUT:    Gemini 2.5 Pro generated response with mid-line Action
        DETECT:   YES (This is the bug fix target)
        RESULT:   has_action=True with correct parameters
        REASON:   Real production case that must work
        """
        response = """Thought:
The user wants me to investigate a Kubernetes alert indicating that the `wes-kasm-dev` namespace is stuck in a terminating state. The alert context points to the `rm1` cluster.

Following the provided runbook, my first step is to retrieve the full details of the namespace to understand its current state, specifically looking at its `status.conditions` and `spec.finalizers`. I will use the `kubernetes-server.resources_get` tool for this.

**Phase 1: Namespace Status Investigation**
*   **Step 1: Retrieve Namespace Details**

I will now get the YAML for the `wes-kasm-dev` namespace.Action: kubernetes-server.resources_get
Action Input:
apiVersion: v1
kind: Namespace
name: wes-kasm-dev
context: rm1
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "CRITICAL: Must parse real Gemini failure case"
        assert parsed.is_malformed is False
        assert parsed.action == "kubernetes-server.resources_get"
        assert parsed.tool_call.server == "kubernetes-server"
        assert parsed.tool_call.tool == "resources_get"
        assert parsed.tool_call.parameters["apiVersion"] == "v1"
        assert parsed.tool_call.parameters["kind"] == "Namespace"
        assert parsed.tool_call.parameters["name"] == "wes-kasm-dev"
        assert parsed.tool_call.parameters["context"] == "rm1"
    
    def test_E2_complex_multi_sentence_thought(self):
        """
        E2: Complex thought with multiple sentences and markdown
        
        INPUT:    Multiple sentences with markdown before mid-line Action
        DETECT:   YES (Tier 3: last period triggers)
        RESULT:   has_action=True, thought preserved up to Action
        REASON:   Real-world LLMs generate complex thoughts with formatting
        """
        response = """Thought:
The namespace `wes-kasm-dev` is stuck in terminating state. This requires investigation.
Following the runbook, I will retrieve the namespace details. This will show status.conditions.
I will use the resources_get tool.Action: kubernetes-server.resources_get
Action Input:
apiVersion: v1
kind: Namespace  
name: wes-kasm-dev
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.has_action is True, "Should handle complex multi-sentence thought"
        assert parsed.action == "kubernetes-server.resources_get"
        assert parsed.tool_call.parameters["kind"] == "Namespace"
        # Thought should be preserved up to the Action
        assert parsed.thought is not None
        assert "stuck" in parsed.thought  # Original thought content present
    
    def test_E3_code_block_mention(self):
        """
        E3: "Action:" mentioned in code block description
        
        INPUT:    "The code shows an Action: statement"
        DETECT:   NO (no sentence boundary before it)
        RESULT:   is_malformed=True
        REASON:   Discussion of code, not an action command
        """
        response = """Thought: The code shows an Action: statement in the function.

We need to handle this carefully.
"""
        parsed = ReActParser.parse_response(response)
        
        assert parsed.is_malformed is True, "Code mention without boundary should NOT be detected"
        assert parsed.has_action is False


@pytest.mark.unit  
class TestParserBoundaryConditions:
    """
    BOUNDARY CONDITIONS: Test edge cases and limits
    
    These tests verify the parser handles unusual inputs gracefully without crashing.
    """
    
    def test_empty_response(self):
        """Empty string should return malformed, not crash"""
        parsed = ReActParser.parse_response("")
        assert parsed.is_malformed is True
    
    def test_none_response(self):
        """None should return malformed, not crash"""
        parsed = ReActParser.parse_response(None)
        assert parsed.is_malformed is True
    
    def test_only_punctuation(self):
        """Response with only punctuation should be malformed"""
        parsed = ReActParser.parse_response("...!!!???")
        assert parsed.is_malformed is True
    
    def test_action_without_tool_name(self):
        """Action: with no tool name should be malformed"""
        response = """Thought: Test.Action:
Action Input: param: value
"""
        parsed = ReActParser.parse_response(response)
        # Should be malformed because Action has no content
        assert parsed.is_malformed is True
    
    def test_action_with_only_server(self):
        """Action: with only server (no dot, no tool) should be unknown tool"""
        response = """Thought: Test.Action: kubectl
Action Input: param: value
"""
        parsed = ReActParser.parse_response(response)
        # Should fail tool call validation (needs server.tool format) - detected as unknown tool
        assert parsed.is_unknown_tool is True
        assert parsed.action == "kubectl"
        assert "Unknown tool 'kubectl'" in parsed.error_message

