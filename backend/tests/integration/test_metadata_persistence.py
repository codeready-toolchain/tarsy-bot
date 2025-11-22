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
    
    def test_response_metadata_persists_to_database(self, test_database_session):
        """Test that response_metadata survives database round-trip with full JSON content."""
        from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
        from tarsy.utils.timestamp import now_us
        
        # Create interaction with complex nested metadata
        expected_metadata = {
            'finish_reason': 'stop',
            'grounding_metadata': {
                'web_search_queries': ['kubernetes pod crash', 'memory leak detection'],
                'grounding_chunks': [
                    {
                        'web': {
                            'uri': 'https://kubernetes.io/docs/troubleshooting',
                            'title': 'Kubernetes Troubleshooting Guide'
                        }
                    },
                    {
                        'web': {
                            'uri': 'https://example.com/debugging',
                            'title': 'Memory Debugging Best Practices'
                        }
                    }
                ],
                'grounding_supports': [
                    {
                        'segment': {
                            'startIndex': 0,
                            'endIndex': 50
                        },
                        'confidenceScores': [0.95, 0.87]
                    }
                ]
            },
            'usage_metadata': {
                'prompt_tokens': 100,
                'completion_tokens': 50,
                'total_tokens': 150
            }
        }
        
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant"),
                LLMMessage(role=MessageRole.USER, content="Help debug my pod"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Based on web search..."),
            ]
        )
        
        interaction = LLMInteraction(
            session_id="test-persistence-session",
            timestamp_us=now_us(),
            model_name="gemini-2.0-flash",
            conversation=conversation,
            response_metadata=expected_metadata
        )
        
        # Persist to database
        test_database_session.add(interaction)
        test_database_session.commit()
        interaction_id = interaction.interaction_id
        
        # Clear session to force fresh read from database
        test_database_session.expire_all()
        
        # Read back from database
        retrieved = test_database_session.query(LLMInteraction).filter_by(interaction_id=interaction_id).first()
        
        assert retrieved is not None, "Failed to retrieve interaction from database"
        assert retrieved.response_metadata is not None, "Metadata was lost during persistence"
        
        # Verify all nested structure survived round-trip
        assert retrieved.response_metadata['finish_reason'] == 'stop'
        assert 'grounding_metadata' in retrieved.response_metadata
        
        grounding = retrieved.response_metadata['grounding_metadata']
        assert len(grounding['web_search_queries']) == 2
        assert 'kubernetes pod crash' in grounding['web_search_queries']
        assert len(grounding['grounding_chunks']) == 2
        assert grounding['grounding_chunks'][0]['web']['uri'] == 'https://kubernetes.io/docs/troubleshooting'
        
        # Verify usage metadata
        assert retrieved.response_metadata['usage_metadata']['total_tokens'] == 150
        
        # Verify complete equality
        assert retrieved.response_metadata == expected_metadata

