"""
Unit tests for ChatAgent.

Tests the built-in chat agent functionality including MCP server configuration,
custom instructions, and strategy-aware controller setup.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.chat_agent import ChatAgent
from tarsy.agents.iteration_controllers.chat_react_controller import ChatReActController
from tarsy.models.constants import IterationStrategy


@pytest.mark.unit
class TestChatAgent:
    """Test ChatAgent functionality."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Mock LLM client for testing."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client for testing."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Mock MCP registry for testing."""
        return Mock()
    
    @pytest.fixture
    def chat_agent(self, mock_llm_manager, mock_mcp_client, mock_mcp_registry):
        """Create ChatAgent instance for testing."""
        return ChatAgent(
            llm_manager=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
    
    def test_mcp_servers_returns_empty_for_dynamic_configuration(self, chat_agent):
        """Test ChatAgent returns empty MCP servers for dynamic configuration from session context."""
        servers = chat_agent.mcp_servers()
        assert servers == []
    
    def test_defaults_to_react_iteration_strategy(self, chat_agent):
        """Test ChatAgent defaults to ReAct iteration strategy."""
        assert chat_agent.iteration_strategy == IterationStrategy.REACT
    
    def test_provides_chat_specific_instructions(self, chat_agent):
        """Test ChatAgent provides instructions appropriate for follow-up conversations."""
        instructions = chat_agent.custom_instructions()
        
        assert instructions is not None
        assert len(instructions) > 0
        assert "follow-up" in instructions.lower() or "investigation" in instructions.lower()
    
    def test_creates_chat_react_controller_for_react_strategy(self, chat_agent):
        """Test ChatAgent creates ChatReActController for REACT strategy."""
        controller = chat_agent._create_iteration_controller(IterationStrategy.REACT)
        
        assert isinstance(controller, ChatReActController)
    
    def test_creates_chat_native_thinking_controller_for_native_thinking_strategy(
        self, mock_llm_manager, mock_mcp_client, mock_mcp_registry
    ):
        """Test ChatAgent creates ChatNativeThinkingController for NATIVE_THINKING strategy."""
        from tarsy.agents.iteration_controllers.chat_native_thinking_controller import (
            ChatNativeThinkingController,
        )
        from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
        
        # Mock the LLM client to return Google provider config
        mock_llm_manager.get_client = Mock(return_value=mock_llm_manager)
        mock_llm_manager.config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-3-pro-preview",
            api_key="test-key",
            api_key_env="GOOGLE_API_KEY"
        )
        mock_llm_manager.provider_name = "test-google"
        
        # Patch GeminiNativeThinkingClient where the controller imports it (NativeThinkingController's module)
        # to avoid creating a real client during agent construction
        with patch(
            'tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient'
        ) as mock_gemini_client_class:
            # Return a harmless mock instance to prevent real client creation
            mock_gemini_client_class.return_value = Mock()
            
            agent = ChatAgent(
                llm_manager=mock_llm_manager,
                mcp_client=mock_mcp_client,
                mcp_registry=mock_mcp_registry,
                iteration_strategy=IterationStrategy.NATIVE_THINKING
            )
        
            # Verify the strategy enum is set correctly
            assert agent.iteration_strategy == IterationStrategy.NATIVE_THINKING
            
            # Verify the actual controller type is ChatNativeThinkingController
            assert isinstance(agent._iteration_controller, ChatNativeThinkingController)
    
    def test_respects_iteration_strategy_parameter(
        self, mock_llm_manager, mock_mcp_client, mock_mcp_registry
    ):
        """Test ChatAgent respects the iteration_strategy parameter."""
        # Create ChatAgent with REACT_STAGE strategy
        agent = ChatAgent(
            llm_manager=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        # Should use the provided strategy (falls back to ChatReActController for non-native-thinking)
        assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
    
    def test_provides_chat_specific_general_instructions(self, chat_agent):
        """Test ChatAgent provides chat-specific general instructions, not alert analysis instructions."""
        general_instructions = chat_agent.get_general_instructions()
        
        assert general_instructions is not None
        assert len(general_instructions) > 0
        
        # Should mention chat/follow-up context
        assert "follow-up" in general_instructions.lower() or "chat" in general_instructions.lower()
        
        # Should NOT mention alert analysis as primary focus
        assert "Analyze alerts thoroughly" not in general_instructions
        
        # Should mention the investigation context
        assert "investigation" in general_instructions.lower()

