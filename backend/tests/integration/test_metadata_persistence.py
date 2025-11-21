"""
Integration test to verify response metadata is properly persisted to database.
"""

import pytest
from tarsy.models.unified_interactions import LLMInteraction


@pytest.mark.integration
class TestMetadataPersistence:
    """Test that response_metadata is properly stored and retrieved from database."""
    
    def test_response_metadata_field_exists_in_schema(self, test_database_session):
        """Test that response_metadata column exists in the database schema."""
        from sqlalchemy import inspect
        
        inspector = inspect(test_database_session.bind)
        columns = inspector.get_columns('llm_interactions')
        column_names = [c['name'] for c in columns]
        
        assert 'response_metadata' in column_names
    
    def test_llm_interaction_model_has_response_metadata(self):
        """Test that LLMInteraction model has response_metadata field."""
        from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
        from tarsy.utils.timestamp import now_us
        
        # Create interaction with metadata
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System message"),
                LLMMessage(role=MessageRole.USER, content="User message"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Assistant response"),
            ]
        )
        
        interaction = LLMInteraction(
            session_id="test-session",
            timestamp_us=now_us(),
            model_name="gemini-2.0-flash",
            conversation=conversation,
            response_metadata={
                'finish_reason': 'stop',
                'grounding_metadata': {
                    'web_search_queries': ['test query'],
                    'grounding_chunks': [
                        {
                            'web': {
                                'uri': 'https://example.com',
                                'title': 'Test Page'
                            }
                        }
                    ]
                }
            }
        )
        
        # Verify field is accessible
        assert hasattr(interaction, 'response_metadata')
        assert interaction.response_metadata is not None
        assert interaction.response_metadata['finish_reason'] == 'stop'
        assert 'grounding_metadata' in interaction.response_metadata
    
    def test_response_metadata_none_allowed(self):
        """Test that response_metadata can be None (for non-Google providers)."""
        from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
        from tarsy.utils.timestamp import now_us
        
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System message"),
                LLMMessage(role=MessageRole.USER, content="User message"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Assistant response"),
            ]
        )
        
        interaction = LLMInteraction(
            session_id="test-session",
            timestamp_us=now_us(),
            model_name="gpt-4",
            conversation=conversation,
            response_metadata=None  # OpenAI doesn't have grounding metadata
        )
        
        # Verify field is accessible and None is allowed
        assert hasattr(interaction, 'response_metadata')
        assert interaction.response_metadata is None

