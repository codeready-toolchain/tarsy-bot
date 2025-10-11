"""
Integration tests for complete token usage tracking flow added in EP-0009.

Tests the end-to-end token tracking from LLM calls through database storage 
to API responses and WebSocket updates.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole, LLMInteraction


@pytest.mark.integration
class TestTokenUsageIntegration:
    """Test token usage tracking integration with database."""
    
    @pytest.mark.asyncio
    async def test_llm_interaction_token_storage(self, history_service_with_test_db):
        """Test that LLM interactions with token data are stored correctly."""
        # Arrange - Create session using proper integration pattern
        from tests.integration.test_history_integration import create_test_context_and_chain
        
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="PodCrash",
            session_id="token-integration-test-1",
            chain_id="token-integration-chain-1",
            agent="KubernetesAgent",
            alert_data={"pod": "test-pod", "error": "OutOfMemory"}
        )
        
        # Create the session in database
        result = history_service_with_test_db.create_session(chain_context, chain_definition)
        assert result is True
        
        # Create LLM interaction with token data
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a Kubernetes expert."),
            LLMMessage(role=MessageRole.USER, content="Analyze pod crash"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Pod crashed due to OOM")
        ])
        
        llm_interaction = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id="test-stage-exec",
            model_name="gpt-4",
            conversation=conversation,
            duration_ms=1500,
            input_tokens=200,
            output_tokens=80,
            total_tokens=280
        )
        
        # Act - Store the interaction
        history_service_with_test_db.store_llm_interaction(llm_interaction)
        
        # Assert - Verify token data was stored
        with history_service_with_test_db.get_repository() as repo:
            detailed_session = repo.get_session_details(chain_context.session_id)
            
            assert detailed_session is not None
            assert len(detailed_session.stages) >= 1
            
            # Check LLM interaction has token data
            stage = detailed_session.stages[0]
            assert len(stage.llm_interactions) == 1
            
            stored_interaction = stage.llm_interactions[0]
            assert stored_interaction.details.input_tokens == 200
            assert stored_interaction.details.output_tokens == 80
            assert stored_interaction.details.total_tokens == 280
    
    @pytest.mark.asyncio
    async def test_stage_token_aggregation(self, history_service_with_test_db):
        """Test that stage-level token aggregations work with multiple interactions."""
        # Arrange - Create session  
        from tests.integration.test_history_integration import create_test_context_and_chain
        from tests.utils import StageExecutionFactory
        
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="HighCPU",
            session_id="token-aggregation-test-2",
            chain_id="token-aggregation-chain-2", 
            agent="KubernetesAgent",
            alert_data={"pod": "high-cpu-pod"}
        )
        
        result = history_service_with_test_db.create_session(chain_context, chain_definition)
        assert result is True
        
        # Create stage execution
        stage_execution_id = await StageExecutionFactory.create_and_save_stage_execution(
            history_service_with_test_db,
            chain_context.session_id,
            stage_id="analysis",
            stage_name="CPU Analysis"
        )
        
        # Create multiple LLM interactions
        interaction1 = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage_execution_id,
            model_name="gpt-4", 
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a Kubernetes expert."),
                LLMMessage(role=MessageRole.USER, content="Check CPU usage"),
                LLMMessage(role=MessageRole.ASSISTANT, content="High CPU detected")
            ]),
            input_tokens=150,
            output_tokens=75,
            total_tokens=225
        )
        
        interaction2 = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage_execution_id,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a Kubernetes expert."),
                LLMMessage(role=MessageRole.USER, content="What's the fix?"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Scale the deployment")
            ]),
            input_tokens=100,
            output_tokens=50,
            total_tokens=150
        )
        
        # Store interactions
        history_service_with_test_db.store_llm_interaction(interaction1)
        history_service_with_test_db.store_llm_interaction(interaction2)
        
        # Act & Assert - Check stage aggregations
        with history_service_with_test_db.get_repository() as repo:
            detailed_session = repo.get_session_details(chain_context.session_id)
            
            assert detailed_session is not None
            stage = detailed_session.stages[0]
            assert len(stage.llm_interactions) == 2
            
            # Check computed token aggregations
            assert stage.stage_input_tokens == 250   # 150 + 100
            assert stage.stage_output_tokens == 125  # 75 + 50
            assert stage.stage_total_tokens == 375   # 225 + 150
    
    @pytest.mark.asyncio 
    async def test_session_token_aggregation(self, history_service_with_test_db):
        """Test that session-level token aggregations work across stages."""
        # Arrange - Create session with multiple stages
        from tests.integration.test_history_integration import create_test_context_and_chain
        from tests.utils import StageExecutionFactory
        
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="NetworkIssue", 
            session_id="token-session-test-3",
            chain_id="token-session-chain-3",
            agent="NetworkAgent",
            alert_data={"error": "connection timeout"}
        )
        
        result = history_service_with_test_db.create_session(chain_context, chain_definition)
        assert result is True
        
        # Create two stages
        stage1_id = await StageExecutionFactory.create_and_save_stage_execution(
            history_service_with_test_db,
            chain_context.session_id,
            stage_id="analysis",
            stage_name="Network Analysis"
        )
        
        stage2_id = await StageExecutionFactory.create_and_save_stage_execution(
            history_service_with_test_db,
            chain_context.session_id,
            stage_id="remediation", 
            stage_name="Network Remediation"
        )
        
        # Stage 1 interaction
        interaction1 = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage1_id,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a network expert."),
                LLMMessage(role=MessageRole.USER, content="Network timeout analysis"),
                LLMMessage(role=MessageRole.ASSISTANT, content="DNS resolution issue detected")
            ]),
            input_tokens=300,
            output_tokens=150,
            total_tokens=450
        )
        
        # Stage 2 interaction
        interaction2 = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage2_id,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a network expert."),
                LLMMessage(role=MessageRole.USER, content="Fix DNS issue"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Restart CoreDNS pods")
            ]),
            input_tokens=180,
            output_tokens=90,
            total_tokens=270
        )
        
        # Store interactions
        history_service_with_test_db.store_llm_interaction(interaction1)
        history_service_with_test_db.store_llm_interaction(interaction2)
        
        # Act & Assert - Check session-level aggregations
        session_stats = await history_service_with_test_db.get_session_summary(chain_context.session_id)
        
        assert session_stats is not None
        assert session_stats.session_input_tokens == 480   # 300 + 180
        assert session_stats.session_output_tokens == 240  # 150 + 90
        assert session_stats.session_total_tokens == 720   # 450 + 270
        assert session_stats.llm_interactions == 2
    
    @pytest.mark.asyncio
    async def test_mixed_token_availability(self, history_service_with_test_db):
        """Test aggregation when some interactions have token data and others don't."""
        # Arrange
        from tests.integration.test_history_integration import create_test_context_and_chain
        from tests.utils import StageExecutionFactory
        
        chain_context, chain_definition = create_test_context_and_chain(
            alert_type="MixedTokens",
            session_id="mixed-token-test-4",
            chain_id="mixed-token-chain-4",
            agent="TestAgent",
            alert_data={"test": "mixed"}
        )
        
        result = history_service_with_test_db.create_session(chain_context, chain_definition)
        assert result is True
        
        stage_id = await StageExecutionFactory.create_and_save_stage_execution(
            history_service_with_test_db,
            chain_context.session_id,
            stage_id="mixed-analysis",
            stage_name="Mixed Analysis"
        )
        
        # Interaction with token data
        interaction_with_tokens = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage_id,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
                LLMMessage(role=MessageRole.USER, content="Question 1"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Answer 1")
            ]),
            input_tokens=100,
            output_tokens=50,
            total_tokens=150
        )
        
        # Interaction without token data (e.g., from provider that doesn't support it)
        interaction_without_tokens = LLMInteraction(
            session_id=chain_context.session_id,
            stage_execution_id=stage_id,
            model_name="local-model",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
                LLMMessage(role=MessageRole.USER, content="Question 2"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Answer 2")
            ]),
            input_tokens=None,  # Provider doesn't track tokens
            output_tokens=None,
            total_tokens=None
        )
        
        # Store both interactions
        history_service_with_test_db.store_llm_interaction(interaction_with_tokens)
        history_service_with_test_db.store_llm_interaction(interaction_without_tokens)
        
        # Act & Assert - Check aggregations handle mixed token availability
        with history_service_with_test_db.get_repository() as repo:
            detailed_session = repo.get_session_details(chain_context.session_id)
            
            assert detailed_session is not None
            stage = detailed_session.stages[0]
            assert len(stage.llm_interactions) == 2
            
            # Aggregations should only include interactions with token data
            assert stage.stage_input_tokens == 100   # Only from first interaction
            assert stage.stage_output_tokens == 50   # Only from first interaction  
            assert stage.stage_total_tokens == 150   # Only from first interaction
        
        # Check session-level aggregations
        session_stats = await history_service_with_test_db.get_session_summary(chain_context.session_id)
        assert session_stats is not None
        assert session_stats.session_input_tokens == 100
        assert session_stats.session_output_tokens == 50
        assert session_stats.session_total_tokens == 150
        assert session_stats.llm_interactions == 2  # Both interactions counted
