"""
Unit tests for ChatAgent.

Tests the built-in chat agent functionality including MCP server configuration,
custom instructions, and ReAct controller setup.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from tarsy.agents.chat_agent import ChatAgent
from tarsy.models.constants import IterationStrategy
from tarsy.agents.iteration_controllers.chat_react_controller import ChatReActController


@pytest.mark.unit
class TestChatAgent:
    """Test ChatAgent functionality."""
    
    @pytest.fixture
    def mock_llm_client(self):
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
    def chat_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Create ChatAgent instance for testing."""
        return ChatAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
    
    def test_mcp_servers_returns_empty_for_dynamic_configuration(self, chat_agent):
        """Test ChatAgent returns empty MCP servers for dynamic configuration from session context."""
        servers = chat_agent.mcp_servers()
        assert servers == []
    
    def test_uses_react_iteration_strategy(self, chat_agent):
        """Test ChatAgent uses ReAct iteration strategy for tool-enabled conversations."""
        assert chat_agent.iteration_strategy == IterationStrategy.REACT
    
    def test_provides_chat_specific_instructions(self, chat_agent):
        """Test ChatAgent provides instructions appropriate for follow-up conversations."""
        instructions = chat_agent.custom_instructions()
        
        assert instructions is not None
        assert len(instructions) > 0
        assert "follow-up" in instructions.lower() or "investigation" in instructions.lower()
    
    def test_creates_chat_react_controller(self, chat_agent):
        """Test ChatAgent creates ChatReActController for handling chat conversations."""
        controller = chat_agent._create_iteration_controller(IterationStrategy.REACT)
        
        assert isinstance(controller, ChatReActController)
    
    def test_always_uses_react_strategy_regardless_of_parameter(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
        """Test ChatAgent always uses REACT strategy even if different strategy is passed."""
        # Try to create ChatAgent with REACT_STAGE strategy (should be ignored)
        agent_with_react_stage = ChatAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        # Should still use REACT strategy
        assert agent_with_react_stage.iteration_strategy == IterationStrategy.REACT
    
    def test_provides_chat_specific_general_instructions(self, chat_agent):
        """Test ChatAgent provides chat-specific general instructions, not alert analysis instructions."""
        general_instructions = chat_agent._get_general_instructions()
        
        assert general_instructions is not None
        assert len(general_instructions) > 0
        
        # Should mention chat/follow-up context
        assert "follow-up" in general_instructions.lower() or "chat" in general_instructions.lower()
        
        # Should NOT mention alert analysis as primary focus
        assert "Analyze alerts thoroughly" not in general_instructions
        
        # Should mention the investigation context
        assert "investigation" in general_instructions.lower()

