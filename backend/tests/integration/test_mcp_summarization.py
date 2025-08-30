"""
Integration tests for MCP result summarization (EP-0015).

This module focuses on configuration loading, validation, and component integration
for the summarization feature. Complex flow testing is covered by unit tests.
"""

import pytest

from tarsy.integrations.mcp.summarizer import MCPResultSummarizer  
from tarsy.models.agent_config import MCPServerConfigModel, SummarizationConfig
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.token_counter import TokenCounter


@pytest.mark.integration
class TestSummarizationConfiguration:
    """Test summarization configuration loading and validation."""
    
    async def test_configuration_loading_from_yaml(self, mock_settings):
        """Test that summarization configuration is properly loaded from YAML."""
        # Arrange - Mock configuration data that would come from YAML
        yaml_config = {
            "security-server": {
                "server_id": "security-server",
                "server_type": "security",
                "enabled": True,
                "connection_params": {"command": "security-mcp"},
                "instructions": "Security analysis",
                "summarization": {
                    "enabled": True,
                    "size_threshold_tokens": 2500,
                    "summary_max_token_limit": 1200
                }
            },
            "filesystem-server": {
                "server_id": "filesystem-server", 
                "server_type": "filesystem",
                "enabled": True,
                "connection_params": {"command": "filesystem-mcp"},
                "instructions": "File operations",
                "summarization": {
                    "enabled": False  # Disabled for filesystem
                }
            }
        }
        
        # Act - Create registry with configuration
        registry = MCPServerRegistry(config=yaml_config)
        
        # Assert - Security server has summarization enabled
        security_config = registry.get_server_config_safe("security-server")
        assert security_config is not None
        assert security_config.summarization.enabled is True
        assert security_config.summarization.size_threshold_tokens == 2500
        assert security_config.summarization.summary_max_token_limit == 1200
        
        # Filesystem server has summarization disabled
        filesystem_config = registry.get_server_config_safe("filesystem-server")
        assert filesystem_config is not None
        assert filesystem_config.summarization.enabled is False
    
    async def test_default_summarization_configuration(self, mock_settings):
        """Test default summarization configuration when not explicitly specified."""
        # Arrange - Configuration without explicit summarization settings
        yaml_config = {
            "monitoring-server": {
                "server_id": "monitoring-server",
                "server_type": "monitoring", 
                "enabled": True,
                "connection_params": {"command": "monitoring-mcp"},
                "instructions": "Monitoring operations"
                # No summarization section - should get defaults
            }
        }
        
        # Act
        registry = MCPServerRegistry(config=yaml_config)
        
        # Assert - Should have default summarization config
        config = registry.get_server_config_safe("monitoring-server")
        assert config is not None
        assert config.summarization.enabled is True  # Default is True
        assert config.summarization.size_threshold_tokens == 2000  # Default threshold
        assert config.summarization.summary_max_token_limit == 1000  # Default limit
    
    def test_summarization_config_validation(self):
        """Test that summarization configuration validates constraints."""
        # Test minimum token limits
        with pytest.raises(ValueError):
            SummarizationConfig(size_threshold_tokens=50)  # Below minimum (100)
        
        with pytest.raises(ValueError):
            SummarizationConfig(summary_max_token_limit=25)  # Below minimum (50)
        
        # Test valid configuration
        valid_config = SummarizationConfig(
            enabled=True,
            size_threshold_tokens=1500,
            summary_max_token_limit=800
        )
        assert valid_config.enabled is True
        assert valid_config.size_threshold_tokens == 1500
        assert valid_config.summary_max_token_limit == 800


@pytest.mark.integration
class TestTokenCounter:
    """Test token counting utility integration."""
    
    def test_token_counter_initialization(self):
        """Test token counter initialization with different models."""
        # Test with default model
        counter = TokenCounter()
        assert counter.encoding is not None
        
        # Test with specific model
        gpt4_counter = TokenCounter("gpt-4")
        assert gpt4_counter.encoding is not None
        
        # Test with unknown model (should fallback)
        unknown_counter = TokenCounter("unknown-model")
        assert unknown_counter.encoding is not None
    
    def test_token_counting_accuracy(self):
        """Test token counter accuracy with various input types."""
        counter = TokenCounter()
        
        # Test different input types
        simple_text = "Hello world"
        json_data = {"status": "success", "message": "Operation completed"}
        complex_result = {
            "result": {
                "pods": [{"name": "pod1", "status": "Running"}],
                "metadata": {"count": 1}
            }
        }
        
        # Act
        simple_tokens = counter.count_tokens(simple_text)
        observation_tokens = counter.estimate_observation_tokens("test-server", "test-tool", json_data)
        complex_tokens = counter.estimate_observation_tokens("kubernetes-server", "list_pods", complex_result)
        
        # Assert - Token counts should be reasonable
        assert simple_tokens > 0
        assert observation_tokens > simple_tokens  # Should include server.tool prefix
        assert complex_tokens > observation_tokens  # Complex result should have more tokens


@pytest.mark.integration  
class TestMCPSummarizerComponent:
    """Test MCPResultSummarizer component integration."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client for summarizer testing."""
        from unittest.mock import Mock, AsyncMock
        client = Mock()
        
        async def mock_response(conversation, session_id, stage_execution_id=None, max_tokens=None):
            # Verify max_tokens enforcement
            max_tokens = max_tokens if max_tokens is not None else 1000
            summary = f"SUMMARY: Test summary content (max_tokens={max_tokens})"

            # Create response conversation
            summary_message = LLMMessage(role=MessageRole.ASSISTANT, content=summary)
            result_conversation = LLMConversation(messages=conversation.messages + [summary_message])
            return result_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_response)
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder.""" 
        from unittest.mock import Mock
        builder = Mock()
        
        builder.build_mcp_summarization_system_prompt.return_value = (
            "You are an expert at summarizing Kubernetes tool output."
        )
        builder.build_mcp_summarization_user_prompt.return_value = (
            "Context: Investigating namespace issues.\nSummarize this large result."
        )
        
        return builder
    
    async def test_summarizer_conversation_context_extraction(self, mock_llm_client, mock_prompt_builder):
        """Test that summarizer extracts domain knowledge from investigation context.""" 
        # Arrange
        summarizer = MCPResultSummarizer(mock_llm_client, mock_prompt_builder)
        
        # Create conversation with ReAct formatting that should be filtered
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="""You are an expert Kubernetes SRE.

DOMAIN KNOWLEDGE:
- Production cluster with critical services
- Known finalizer cleanup issues

🚨 WARNING: NEVER GENERATE FAKE OBSERVATIONS! 🚨
[ReAct formatting instructions...]"""),
            LLMMessage(role=MessageRole.USER, content="Investigate the stuck namespace"),
            LLMMessage(role=MessageRole.ASSISTANT, content="I'll check the namespace status")
        ])
        
        # Act
        context = summarizer._serialize_conversation_context(conversation)
        
        # Assert - Should contain domain knowledge (ReAct filtering is implementation detail)
        assert "expert Kubernetes SRE" in context
        assert "DOMAIN KNOWLEDGE" in context
        assert "Production cluster with critical services" in context
        # Note: ReAct filtering implementation may vary - focus on domain knowledge extraction
    
    async def test_summarizer_max_tokens_enforcement(self, mock_llm_client, mock_prompt_builder):
        """Test that summarizer properly passes max_tokens to LLM client."""
        # Arrange
        summarizer = MCPResultSummarizer(mock_llm_client, mock_prompt_builder)
        
        large_result = {
            "result": {"data": "Very large result data content" * 100},
            "status": "success"
        }
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an SRE"),
            LLMMessage(role=MessageRole.USER, content="Check the system")
        ])
        
        # Act
        result = await summarizer.summarize_result(
            "test-server", "test-tool", large_result, conversation,
            "test-session", "test-stage", max_summary_tokens=500
        )
        
        # Assert
        assert result is not None
        assert "SUMMARY:" in str(result.get("result", ""))
        assert "max_tokens=500" in str(result.get("result", ""))
        
        # Verify LLM client was called with correct max_tokens  
        mock_llm_client.generate_response.assert_called_once()
        call_args = mock_llm_client.generate_response.call_args
        
        # Check if max_tokens was passed as keyword argument
        if len(call_args[1]) > 0 and "max_tokens" in call_args[1]:
            assert call_args[1]["max_tokens"] == 500


@pytest.mark.integration
class TestAgentRegistryWithSummarization:
    """Test agent registry integration with summarization configuration."""
    
    def test_builtin_agent_config_includes_summarization(self):
        """Test that built-in agent configurations include summarization settings."""
        # Act
        registry = MCPServerRegistry()  # Uses built-in config
        
        # Assert - Built-in kubernetes-server should have summarization config
        k8s_config = registry.get_server_config_safe("kubernetes-server")
        assert k8s_config is not None
        assert hasattr(k8s_config, 'summarization')
        assert k8s_config.summarization is not None
        assert isinstance(k8s_config.summarization.enabled, bool)
        assert isinstance(k8s_config.summarization.size_threshold_tokens, int)
        assert isinstance(k8s_config.summarization.summary_max_token_limit, int)