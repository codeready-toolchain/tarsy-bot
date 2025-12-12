"""
Test that AlertSession.chain_config property works with old database records.

Simulates the exact scenario from the error log where old sessions have
chat_enabled in their chain_definition JSON.
"""

import pytest

from tarsy.models.agent_config import ChainConfigModel
from tarsy.models.db_models import AlertSession


@pytest.mark.unit
class TestChainConfigPropertyBackwardCompatibility:
    """Test AlertSession.chain_config property with legacy data."""

    def test_chain_config_property_with_old_chat_enabled_field(self):
        """Test that chain_config property handles old chat_enabled field."""
        # Simulate an old database record with chat_enabled in chain_definition
        session = AlertSession(
            session_id="e5d5513f-929f-440f-8bbe-dc24f4926a7f",
            agent_type="chain:test-chain",
            alert_type="TestAlert",
            status="completed",
            chain_id="test-chain",
            chain_definition={
                "chain_id": "test-chain",
                "alert_types": ["TestAlert"],
                "stages": [{"name": "initial-analysis", "agent": "TestAgent"}],
                "chat_enabled": True,  # OLD field that caused the error
            },
        )

        # This should NOT raise ValidationError anymore
        chain_config = session.chain_config

        # Verify the migration worked
        assert chain_config is not None
        assert isinstance(chain_config, ChainConfigModel)
        assert chain_config.chat is not None
        assert chain_config.chat.enabled is True
        assert chain_config.chain_id == "test-chain"

    def test_chain_config_property_with_new_structure(self):
        """Test that chain_config property still works with new structure."""
        session = AlertSession(
            session_id="test-session-2",
            agent_type="chain:test-chain",
            alert_type="TestAlert",
            status="completed",
            chain_id="test-chain",
            chain_definition={
                "chain_id": "test-chain",
                "alert_types": ["TestAlert"],
                "stages": [{"name": "initial-analysis", "agent": "TestAgent"}],
                "chat": {  # NEW structure
                    "enabled": False,
                    "agent": "CustomChatAgent",
                },
            },
        )

        chain_config = session.chain_config

        assert chain_config is not None
        assert chain_config.chat is not None
        assert chain_config.chat.enabled is False
        assert chain_config.chat.agent == "CustomChatAgent"

    def test_chain_config_property_with_none_chain_definition(self):
        """Test that chain_config returns None when chain_definition is None."""
        session = AlertSession(
            session_id="test-session-3",
            agent_type="chain:test-chain",
            alert_type="TestAlert",
            status="pending",
            chain_id="test-chain",
            chain_definition=None,
        )

        chain_config = session.chain_config

        assert chain_config is None

    def test_multiple_old_sessions_can_be_accessed(self):
        """Test that multiple old sessions can be accessed without errors."""
        # Simulate multiple old sessions (like in a list endpoint)
        old_sessions = [
            AlertSession(
                session_id=f"old-session-{i}",
                agent_type="chain:test-chain",
                alert_type="TestAlert",
                status="completed",
                chain_id="test-chain",
                chain_definition={
                    "chain_id": "test-chain",
                    "alert_types": ["TestAlert"],
                    "stages": [{"name": "analysis", "agent": "TestAgent"}],
                    "chat_enabled": i % 2 == 0,  # Mix of True/False
                },
            )
            for i in range(5)
        ]

        # Should be able to access all without errors
        for session in old_sessions:
            config = session.chain_config
            assert config is not None
            assert config.chat is not None
            # Verify the boolean was preserved correctly
            expected_enabled = int(session.session_id.split("-")[-1]) % 2 == 0
            assert config.chat.enabled == expected_enabled
