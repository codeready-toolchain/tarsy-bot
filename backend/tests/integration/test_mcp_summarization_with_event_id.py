"""
Integration tests for MCP result summarization with mcp_event_id tracking.

Tests the end-to-end flow of summarization with mcp_event_id linking
summarization LLM interactions to their corresponding tool calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import Session, select

from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import (
    LLMConversation,
    LLMInteraction,
    LLMMessage,
    MessageRole,
)


@pytest.mark.integration
class TestMCPSummarizationWithEventID:
    """Test end-to-end summarization with mcp_event_id tracking."""
    
    @pytest.mark.asyncio
    async def test_summarization_persists_mcp_event_id_to_database(
        self, test_database_session: Session
    ):
        """Test that mcp_event_id is persisted to database with LLM interaction."""
        # Create mock LLM client
        mock_llm_client = MagicMock()
        mock_llm_client.get_max_tool_result_tokens.return_value = 150000
        
        # Create mock prompt builder
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_mcp_summarization_system_prompt.return_value = "System"
        mock_prompt_builder.build_mcp_summarization_user_prompt.return_value = "User prompt"
        
        # Mock LLM response
        summary_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Summary result"),
            ]
        )
        mock_llm_client.generate_response = AsyncMock(return_value=summary_conversation)
        
        # Create summarizer
        summarizer = MCPResultSummarizer(mock_llm_client, mock_prompt_builder)
        
        # Test data
        test_result = {"result": "Large tool output"}
        investigation_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Investigation"),
            ]
        )
        
        # Execute summarization with mcp_event_id
        await summarizer.summarize_result(
            server_name="kubectl",
            tool_name="get_pods",
            result=test_result,
            investigation_conversation=investigation_conversation,
            session_id="test-session-integration",
            stage_execution_id="stage-integration",
            mcp_event_id="mcp-event-integration-123"
        )
        
        # Verify the LLM client was called with correct parameters
        call_kwargs = mock_llm_client.generate_response.call_args.kwargs
        assert call_kwargs["interaction_type"] == LLMInteractionType.SUMMARIZATION.value
        assert call_kwargs["mcp_event_id"] == "mcp-event-integration-123"
    
    @pytest.mark.asyncio
    async def test_llm_interaction_with_mcp_event_id_database_persistence(
        self, test_database_session: Session
    ):
        """Test that LLMInteraction with mcp_event_id can be saved and retrieved from database."""
        # Create a conversation
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Summarization system prompt"),
                LLMMessage(role=MessageRole.USER, content="Tool result to summarize"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Concise summary"),
            ]
        )
        
        # Create LLM interaction with mcp_event_id
        interaction = LLMInteraction(
            session_id="test-session-db",
            stage_execution_id="stage-db",
            model_name="gpt-4",
            provider="openai",
            temperature=0.1,
            conversation=conversation,
            interaction_type=LLMInteractionType.SUMMARIZATION.value,
            mcp_event_id="mcp-event-db-persist-456",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            success=True,
            duration_ms=1200
        )
        
        # Save to database
        test_database_session.add(interaction)
        test_database_session.commit()
        test_database_session.refresh(interaction)
        
        # Retrieve from database
        stmt = select(LLMInteraction).where(
            LLMInteraction.interaction_id == interaction.interaction_id
        )
        retrieved_interaction = test_database_session.exec(stmt).first()
        
        # Verify all fields including mcp_event_id
        assert retrieved_interaction is not None
        assert retrieved_interaction.session_id == "test-session-db"
        assert retrieved_interaction.interaction_type == LLMInteractionType.SUMMARIZATION.value
        assert retrieved_interaction.mcp_event_id == "mcp-event-db-persist-456"
        assert retrieved_interaction.input_tokens == 100
        assert retrieved_interaction.output_tokens == 50
        assert retrieved_interaction.total_tokens == 150
    
    @pytest.mark.asyncio
    async def test_query_llm_interactions_by_mcp_event_id(
        self, test_database_session: Session
    ):
        """Test querying LLM interactions by mcp_event_id."""
        # Create multiple interactions, some with mcp_event_id
        interactions = [
            LLMInteraction(
                session_id="session-1",
                model_name="gpt-4",
                conversation=LLMConversation(
                    messages=[
                        LLMMessage(role=MessageRole.SYSTEM, content="System"),
                        LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
                    ]
                ),
                interaction_type=LLMInteractionType.INVESTIGATION.value,
                # No mcp_event_id
            ),
            LLMInteraction(
                session_id="session-1",
                model_name="gpt-4",
                conversation=LLMConversation(
                    messages=[
                        LLMMessage(role=MessageRole.SYSTEM, content="System"),
                        LLMMessage(role=MessageRole.ASSISTANT, content="Summary 1"),
                    ]
                ),
                interaction_type=LLMInteractionType.SUMMARIZATION.value,
                mcp_event_id="mcp-event-query-1"
            ),
            LLMInteraction(
                session_id="session-1",
                model_name="gpt-4",
                conversation=LLMConversation(
                    messages=[
                        LLMMessage(role=MessageRole.SYSTEM, content="System"),
                        LLMMessage(role=MessageRole.ASSISTANT, content="Summary 2"),
                    ]
                ),
                interaction_type=LLMInteractionType.SUMMARIZATION.value,
                mcp_event_id="mcp-event-query-2"
            ),
        ]
        
        for interaction in interactions:
            test_database_session.add(interaction)
        test_database_session.commit()
        
        # Query by specific mcp_event_id
        stmt = select(LLMInteraction).where(
            LLMInteraction.mcp_event_id == "mcp-event-query-1"
        )
        result = test_database_session.exec(stmt).first()
        
        assert result is not None
        assert result.mcp_event_id == "mcp-event-query-1"
        assert "Summary 1" in result.conversation.get_latest_assistant_message().content
        
        # Query all interactions with mcp_event_id (summarizations linked to tool calls)
        stmt = select(LLMInteraction).where(
            LLMInteraction.mcp_event_id.isnot(None)  # type: ignore
        )
        results = test_database_session.exec(stmt).all()
        
        assert len(results) == 2
        assert all(r.mcp_event_id is not None for r in results)
        assert all(r.interaction_type == LLMInteractionType.SUMMARIZATION.value for r in results)
    
    @pytest.mark.asyncio
    async def test_multiple_summarizations_same_session_different_mcp_events(
        self, test_database_session: Session
    ):
        """Test that multiple summarizations in same session have different mcp_event_ids."""
        session_id = "multi-summary-session"
        
        # Create three summarization interactions with different mcp_event_ids
        for i in range(3):
            interaction = LLMInteraction(
                session_id=session_id,
                model_name="gpt-4",
                conversation=LLMConversation(
                    messages=[
                        LLMMessage(role=MessageRole.SYSTEM, content="System"),
                        LLMMessage(role=MessageRole.ASSISTANT, content=f"Summary {i}"),
                    ]
                ),
                interaction_type=LLMInteractionType.SUMMARIZATION.value,
                mcp_event_id=f"mcp-event-multi-{i}"
            )
            test_database_session.add(interaction)
        
        test_database_session.commit()
        
        # Query all summarizations for this session
        stmt = select(LLMInteraction).where(
            LLMInteraction.session_id == session_id,
            LLMInteraction.interaction_type == LLMInteractionType.SUMMARIZATION.value
        )
        results = test_database_session.exec(stmt).all()
        
        assert len(results) == 3
        
        # Verify each has a unique mcp_event_id
        mcp_event_ids = [r.mcp_event_id for r in results]
        assert len(set(mcp_event_ids)) == 3  # All unique
        assert "mcp-event-multi-0" in mcp_event_ids
        assert "mcp-event-multi-1" in mcp_event_ids
        assert "mcp-event-multi-2" in mcp_event_ids
    
    @pytest.mark.asyncio
    async def test_llm_interaction_without_mcp_event_id_still_works(
        self, test_database_session: Session
    ):
        """Test that LLM interactions without mcp_event_id work correctly (backward compatibility)."""
        # Create interaction without mcp_event_id
        interaction = LLMInteraction(
            session_id="backward-compat-session",
            model_name="gpt-4",
            conversation=LLMConversation(
                messages=[
                    LLMMessage(role=MessageRole.SYSTEM, content="System"),
                    LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
                ]
            ),
            interaction_type=LLMInteractionType.INVESTIGATION.value
            # No mcp_event_id
        )
        
        test_database_session.add(interaction)
        test_database_session.commit()
        test_database_session.refresh(interaction)
        
        # Retrieve and verify
        stmt = select(LLMInteraction).where(
            LLMInteraction.session_id == "backward-compat-session"
        )
        result = test_database_session.exec(stmt).first()
        
        assert result is not None
        assert result.mcp_event_id is None
        assert result.interaction_type == LLMInteractionType.INVESTIGATION.value

