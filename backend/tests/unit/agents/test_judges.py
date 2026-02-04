"""Tests for judge prompts and hashing."""

import hashlib
from tarsy.agents.prompts.judges import (
    JUDGE_PROMPT_SCORE,
    JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS,
    get_current_prompt_hash,
    CURRENT_PROMPT_HASH,
)


class TestJudgePrompts:
    """Test judge prompt constants."""

    def test_judge_prompt_score_contains_placeholders(self):
        """Test that JUDGE_PROMPT_SCORE contains required placeholders."""
        assert "{{SESSION_CONVERSATION}}" in JUDGE_PROMPT_SCORE
        assert "{{ALERT_DATA}}" in JUDGE_PROMPT_SCORE
        assert "{{OUTPUT_SCHEMA}}" in JUDGE_PROMPT_SCORE

    def test_judge_prompt_followup_contains_content(self):
        """Test that JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS is non-empty."""
        assert len(JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS) > 0
        assert "missing tool" in JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS.lower()


class TestPromptHashing:
    """Test SHA256 hashing logic for prompt versioning."""

    def test_hash_determinism(self):
        """Test that hashing produces consistent results."""
        hash1 = get_current_prompt_hash()
        hash2 = get_current_prompt_hash()

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_hash_matches_module_constant(self):
        """Test that module-level CURRENT_PROMPT_HASH matches function result."""
        computed_hash = get_current_prompt_hash()
        assert CURRENT_PROMPT_HASH == computed_hash

    def test_hash_is_hex_string(self):
        """Test that hash is a valid hexadecimal string."""
        assert all(c in "0123456789abcdef" for c in CURRENT_PROMPT_HASH)
        assert len(CURRENT_PROMPT_HASH) == 64
