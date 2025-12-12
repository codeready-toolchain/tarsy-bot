"""
Tests for ChainConfigModel backward compatibility with old chat_enabled field.

Validates that old database records with chat_enabled field are automatically
migrated to the new chat structure during model instantiation.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.agent_config import ChainConfigModel


@pytest.mark.unit
class TestChainConfigBackwardCompatibility:
    """Test backward compatibility for chat_enabled -> chat migration."""

    def test_old_chat_enabled_true_migrates_to_new_structure(self):
        """Old chat_enabled: true should become chat: {enabled: true}."""
        old_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
            "chat_enabled": True,  # Old field
        }

        config = ChainConfigModel(**old_config)

        # Should have migrated to new structure
        assert config.chat is not None
        assert config.chat.enabled is True

    def test_old_chat_enabled_false_migrates_to_new_structure(self):
        """Old chat_enabled: false should become chat: {enabled: false}."""
        old_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
            "chat_enabled": False,  # Old field
        }

        config = ChainConfigModel(**old_config)

        # Should have migrated to new structure
        assert config.chat is not None
        assert config.chat.enabled is False

    def test_new_chat_structure_takes_precedence_over_old(self):
        """If both chat and chat_enabled exist, new chat structure wins."""
        mixed_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
            "chat_enabled": True,  # Old field
            "chat": {  # New structure (should take precedence)
                "enabled": False,
                "agent": "CustomChatAgent",
            },
        }

        config = ChainConfigModel(**mixed_config)

        # New structure should take precedence
        assert config.chat is not None
        assert config.chat.enabled is False
        assert config.chat.agent == "CustomChatAgent"

    def test_new_chat_structure_works_normally(self):
        """New chat structure should work without any migration."""
        new_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
            "chat": {"enabled": True, "agent": "ChatAgent", "llm_provider": "openai"},
        }

        config = ChainConfigModel(**new_config)

        assert config.chat is not None
        assert config.chat.enabled is True
        assert config.chat.agent == "ChatAgent"
        assert config.chat.llm_provider == "openai"

    def test_no_chat_field_uses_default(self):
        """Missing chat field should use default (enabled=True)."""
        minimal_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
        }

        config = ChainConfigModel(**minimal_config)

        # Should use default ChatConfig (enabled=True)
        assert config.chat is not None
        assert config.chat.enabled is True

    def test_old_chat_enabled_removed_after_migration(self):
        """chat_enabled field should not remain in the model after migration."""
        old_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
            "chat_enabled": True,
        }

        config = ChainConfigModel(**old_config)

        # chat_enabled should not be in the model (extra='forbid' would reject it)
        # This test verifies the migration properly removes the old field
        assert not hasattr(config, "chat_enabled")

        # Should be able to dump model without errors
        dumped = config.model_dump()
        assert "chat_enabled" not in dumped
        assert "chat" in dumped
        assert dumped["chat"]["enabled"] is True

    def test_extra_fields_still_rejected(self):
        """Other extra fields should still be rejected (extra='forbid')."""
        invalid_config = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"name": "analysis", "agent": "TestAgent"}],
            "unknown_field": "should_fail",  # This should fail
        }

        with pytest.raises(ValidationError) as exc_info:
            ChainConfigModel(**invalid_config)

        # Should complain about extra field
        assert "extra_forbidden" in str(exc_info.value)
