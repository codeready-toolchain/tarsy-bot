"""
Unit tests for MCP configuration resolution service.

Tests the hierarchical resolution of MCP server configuration across
agent, chain, stage, and parallel-agent levels.
"""

import pytest

from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    ParallelAgentConfig,
)
from tarsy.services.mcp_config_resolver import MCPConfigResolver

@pytest.mark.unit
class TestMCPConfigResolver:
    """Test suite for MCPConfigResolver."""
    
    def test_resolve_no_config(self):
        """Test resolution when no configuration is provided."""
        result = MCPConfigResolver.resolve_mcp_servers()
        assert result is None
    
    def test_resolve_agent_level_only(self):
        """Test resolution with only agent-level configuration."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server-1", "agent-server-2"],
            custom_instructions="test"
        )
        
        result = MCPConfigResolver.resolve_mcp_servers(agent_config=agent_config)
        assert result == ["agent-server-1", "agent-server-2"]
    
    def test_resolve_chain_level_overrides_agent(self):
        """Test that chain-level overrides agent-level."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test"
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="test-stage", agent="TestAgent")],
            mcp_servers=["chain-server"]
        )
        
        result = MCPConfigResolver.resolve_mcp_servers(
            agent_config=agent_config,
            chain_config=chain_config
        )
        assert result == ["chain-server"]
    
    def test_resolve_stage_level_overrides_chain_and_agent(self):
        """Test that stage-level overrides both chain and agent levels."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test"
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=["chain-server"]
        )
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            mcp_servers=["stage-server"]
        )
        
        result = MCPConfigResolver.resolve_mcp_servers(
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        assert result == ["stage-server"]
    
    def test_resolve_parallel_agent_level_highest_priority(self):
        """Test that parallel-agent level has highest priority."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test"
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=["chain-server"]
        )
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            mcp_servers=["stage-server"]
        )
        parallel_agent_config = ParallelAgentConfig(
            name="ParallelAgent",
            mcp_servers=["parallel-server"]
        )
        
        result = MCPConfigResolver.resolve_mcp_servers(
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config
        )
        assert result == ["parallel-server"]
    
    def test_resolve_skips_none_values(self):
        """Test that None values are skipped and next level is used."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test"
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=None  # Not specified
        )
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            mcp_servers=["stage-server"]
        )
        
        # Stage overrides agent (chain is None)
        result = MCPConfigResolver.resolve_mcp_servers(
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        assert result == ["stage-server"]
    
    def test_resolve_multiple_servers_at_parallel_level(self):
        """Test resolution with multiple servers at parallel-agent level."""
        parallel_agent_config = ParallelAgentConfig(
            name="ParallelAgent",
            mcp_servers=["server-1", "server-2", "server-3"]
        )
        
        result = MCPConfigResolver.resolve_mcp_servers(
            parallel_agent_config=parallel_agent_config
        )
        assert result == ["server-1", "server-2", "server-3"]
    
    def test_resolve_none_when_all_none(self):
        """Test that None is returned when all levels are None."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test"
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=None
        )
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            mcp_servers=None
        )
        
        # Agent level has servers, but it's the lowest priority
        # Chain and stage are None, so agent level is used
        result = MCPConfigResolver.resolve_mcp_servers(
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        assert result == ["agent-server"]
    
    def test_synthesis_config_mcp_servers(self):
        """Test that SynthesisConfig can have mcp_servers field."""
        from tarsy.models.agent_config import SynthesisConfig
        
        # Test that synthesis config accepts mcp_servers
        synthesis_config = SynthesisConfig(
            agent="SynthesisAgent",
            iteration_strategy="synthesis",
            llm_provider="google-default",
            mcp_servers=["kubernetes-server", "monitoring-server"]
        )
        
        assert synthesis_config.mcp_servers == ["kubernetes-server", "monitoring-server"]
        assert synthesis_config.agent == "SynthesisAgent"
        
        # Test that synthesis config works without mcp_servers (optional)
        synthesis_config_no_mcp = SynthesisConfig(
            agent="SynthesisAgent",
            iteration_strategy="synthesis"
        )
        
        assert synthesis_config_no_mcp.mcp_servers is None
