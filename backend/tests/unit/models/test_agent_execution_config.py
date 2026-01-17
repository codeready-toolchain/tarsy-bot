"""
Unit tests for AgentExecutionConfig dataclass.

Tests the aggregate configuration object used for agent execution.
"""

import pytest

from tarsy.models.agent_execution_config import AgentExecutionConfig

@pytest.mark.unit
class TestAgentExecutionConfig:
    """Test suite for AgentExecutionConfig."""
    
    def test_create_with_all_fields(self):
        """Test creation with all fields specified."""
        config = AgentExecutionConfig(
            llm_provider="test-provider",
            iteration_strategy="react",
            max_iterations=25,
            force_conclusion=True,
            mcp_servers=["server-1", "server-2"]
        )
        
        assert config.llm_provider == "test-provider"
        assert config.iteration_strategy == "react"
        assert config.max_iterations == 25
        assert config.force_conclusion is True
        assert config.mcp_servers == ["server-1", "server-2"]
    
    def test_create_with_defaults(self):
        """Test creation with default None values."""
        config = AgentExecutionConfig()
        
        assert config.llm_provider is None
        assert config.iteration_strategy is None
        assert config.max_iterations is None
        assert config.force_conclusion is None
        assert config.mcp_servers is None
    
    def test_create_with_partial_fields(self):
        """Test creation with only some fields specified."""
        config = AgentExecutionConfig(
            llm_provider="test-provider",
            max_iterations=30
        )
        
        assert config.llm_provider == "test-provider"
        assert config.max_iterations == 30
        # Unspecified fields should be None
        assert config.iteration_strategy is None
        assert config.force_conclusion is None
        assert config.mcp_servers is None
    
    def test_fields_are_mutable(self):
        """Test that config fields can be modified after creation."""
        config = AgentExecutionConfig()
        
        config.llm_provider = "new-provider"
        config.max_iterations = 40
        
        assert config.llm_provider == "new-provider"
        assert config.max_iterations == 40
    
    def test_mcp_servers_empty_list(self):
        """Test that empty list is preserved for mcp_servers."""
        config = AgentExecutionConfig(mcp_servers=[])
        
        assert config.mcp_servers == []
        assert config.mcp_servers is not None
