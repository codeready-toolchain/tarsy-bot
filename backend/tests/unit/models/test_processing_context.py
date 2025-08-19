"""
Unit tests for the new processing context models.

This module tests the clean context architecture that replaces the old
AlertProcessingData, IterationContext, PromptContext, and ChainExecutionContext.
"""

import pytest
from unittest.mock import Mock
from typing import Dict, Any, List
from pydantic import ValidationError

from tarsy.models.processing_context import (
    MCPTool,
    AvailableTools,
    ChainContext,
    StageContext
)
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import StageStatus


class TestMCPTool:
    """Test MCPTool model."""
    
    def test_mcp_tool_creation(self):
        """Test creating an MCPTool with all fields."""
        tool = MCPTool(
            server="kubernetes-server",
            name="get_pods",
            description="Get pod information",
            parameters=[{"name": "namespace", "type": "string"}]
        )
        
        assert tool.server == "kubernetes-server"
        assert tool.name == "get_pods"
        assert tool.description == "Get pod information"
        assert len(tool.parameters) == 1
        assert tool.parameters[0]["name"] == "namespace"
    
    def test_mcp_tool_defaults(self):
        """Test MCPTool with default parameters."""
        tool = MCPTool(
            server="test-server",
            name="test_tool",
            description="Test description"
        )
        
        assert tool.parameters == []
    
    def test_mcp_tool_validation(self):
        """Test MCPTool field validation."""
        with pytest.raises(ValidationError):
            MCPTool(server="", name="test", description="test")
        
        with pytest.raises(ValidationError):
            MCPTool(server="test", name="", description="test")


class TestAvailableTools:
    """Test AvailableTools model."""
    
    def test_available_tools_empty(self):
        """Test empty AvailableTools."""
        tools = AvailableTools()
        assert tools.tools == []
        assert tools.to_prompt_format() == "No tools available."
    
    def test_available_tools_with_mcp_tools(self):
        """Test AvailableTools with structured MCPTool objects."""
        mcp_tool = MCPTool(
            server="k8s",
            name="get_pods",
            description="Get Kubernetes pods"
        )
        
        tools = AvailableTools(tools=[mcp_tool])
        
        assert len(tools.tools) == 1
        assert isinstance(tools.tools[0], MCPTool)
        
        prompt_format = tools.to_prompt_format()
        assert "k8s.get_pods: Get Kubernetes pods" in prompt_format


class TestChainContext:
    """Test ChainContext model."""
    
    def test_chain_context_creation(self):
        """Test creating ChainContext with all required fields."""
        context = ChainContext(
            alert_type="kubernetes",
            alert_data={"pod": "failing-pod", "namespace": "default"},
            session_id="session-123",
            current_stage_name="analysis"
        )
        
        assert context.alert_type == "kubernetes"
        assert context.alert_data["pod"] == "failing-pod"
        assert context.session_id == "session-123"
        assert context.current_stage_name == "analysis"
        assert context.stage_outputs == {}
        assert context.runbook_content is None
        assert context.chain_id is None
    
    def test_chain_context_with_optional_fields(self):
        """Test ChainContext with optional fields populated."""
        stage_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            timestamp_us=1234567890,
            result_summary="Stage completed successfully"
        )
        
        context = ChainContext(
            alert_type="aws",
            alert_data={"instance_id": "i-123"},
            session_id="session-456",
            current_stage_name="investigation",
            runbook_content="# Investigation Runbook",
            chain_id="chain-789"
        )
        context.add_stage_result("previous_stage", stage_result)
        
        assert context.runbook_content == "# Investigation Runbook"
        assert context.chain_id == "chain-789"
        assert len(context.stage_outputs) == 1
        assert "previous_stage" in context.stage_outputs
    
    def test_get_original_alert_data(self):
        """Test getting original alert data as copy."""
        original_data = {"key": "value", "number": 42}
        context = ChainContext(
            alert_type="test",
            alert_data=original_data,
            session_id="test-session",
            current_stage_name="test-stage"
        )
        
        retrieved_data = context.get_original_alert_data()
        
        # Should be a copy, not the same object
        assert retrieved_data == original_data
        assert retrieved_data is not original_data
        
        # Modifying retrieved data shouldn't affect original
        retrieved_data["new_key"] = "new_value"
        assert "new_key" not in context.alert_data
    
    def test_get_runbook_content(self):
        """Test getting runbook content with defaults."""
        # Test with no runbook content
        context = ChainContext(
            alert_type="test",
            alert_data={"test": "data"},
            session_id="test-session",
            current_stage_name="test-stage"
        )
        assert context.get_runbook_content() == ""
        
        # Test with runbook content
        context.runbook_content = "# Test Runbook\nInstructions here"
        assert context.get_runbook_content() == "# Test Runbook\nInstructions here"
    
    def test_add_stage_result(self):
        """Test adding stage results."""
        context = ChainContext(
            alert_type="test",
            alert_data={"test": "data"},
            session_id="test-session",
            current_stage_name="current-stage"
        )
        
        result1 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent1",
            timestamp_us=1234567890,
            result_summary="First stage completed"
        )
        result2 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent2",
            timestamp_us=1234567891,
            result_summary="Second stage completed"
        )
        
        context.add_stage_result("stage1", result1)
        context.add_stage_result("stage2", result2)
        
        assert len(context.stage_outputs) == 2
        assert context.stage_outputs["stage1"] == result1
        assert context.stage_outputs["stage2"] == result2
    
    def test_get_previous_stages_results_empty(self):
        """Test getting previous stages when none exist."""
        context = ChainContext(
            alert_type="test",
            alert_data={"test": "data"},
            session_id="test-session",
            current_stage_name="first-stage"
        )
        
        results = context.get_previous_stages_results()
        assert results == []
    
    def test_get_previous_stages_results_with_completed_stages(self):
        """Test getting previous stages with completed results."""
        context = ChainContext(
            alert_type="test",
            alert_data={"test": "data"},
            session_id="test-session",
            current_stage_name="current-stage"
        )
        
        # Add completed stage
        completed_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="CompletedAgent",
            timestamp_us=1234567890,
            result_summary="Completed stage result"
        )
        context.add_stage_result("completed_stage", completed_result)
        
        # Add running stage (should be excluded)
        running_result = AgentExecutionResult(
            status=StageStatus.ACTIVE,
            agent_name="RunningAgent",
            timestamp_us=1234567891,
            result_summary="Running stage result"
        )
        context.add_stage_result("running_stage", running_result)
        
        results = context.get_previous_stages_results()
        
        assert len(results) == 1
        assert results[0] == ("completed_stage", completed_result)
    
    def test_get_previous_stages_results_preserves_order(self):
        """Test that previous stages results preserve insertion order."""
        context = ChainContext(
            alert_type="test",
            alert_data={"test": "data"},
            session_id="test-session",
            current_stage_name="current-stage"
        )
        
        # Add stages in specific order
        result1 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent1",
            timestamp_us=1234567890,
            result_summary="First stage completed"
        )
        result2 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent2",
            timestamp_us=1234567891,
            result_summary="Second stage completed"
        )
        result3 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent3",
            timestamp_us=1234567892,
            result_summary="Third stage completed"
        )
        
        context.add_stage_result("stage1", result1)
        context.add_stage_result("stage2", result2)
        context.add_stage_result("stage3", result3)
        
        results = context.get_previous_stages_results()
        
        # Should maintain insertion order
        assert len(results) == 3
        assert results[0] == ("stage1", result1)
        assert results[1] == ("stage2", result2)
        assert results[2] == ("stage3", result3)
    
    def test_chain_context_field_validation(self):
        """Test field validation in ChainContext."""
        # Test empty alert_type
        with pytest.raises(ValidationError):
            ChainContext(
                alert_type="",
                alert_data={"test": "data"},
                session_id="test-session",
                current_stage_name="test-stage"
            )
        
        # Test empty alert_data - EP-0012 validation should reject this
        with pytest.raises(ValidationError):
            ChainContext(
                alert_type="test",
                alert_data={},  # Empty dict should raise ValidationError
                session_id="test-session", 
                current_stage_name="test-stage"
            )
        
        # Test empty session_id
        with pytest.raises(ValidationError):
            ChainContext(
                alert_type="test",
                alert_data={"test": "data"},
                session_id="",
                current_stage_name="test-stage"
            )
        
        # Test empty current_stage_name
        with pytest.raises(ValidationError):
            ChainContext(
                alert_type="test",
                alert_data={"test": "data"},
                session_id="test-session",
                current_stage_name=""
            )


class TestStageContext:
    """Test StageContext model."""
    
    def create_test_chain_context(self) -> ChainContext:
        """Create a test ChainContext for StageContext tests."""
        return ChainContext(
            alert_type="kubernetes",
            alert_data={"pod": "test-pod", "namespace": "default"},
            session_id="test-session-123",
            current_stage_name="analysis",
            runbook_content="# Test Runbook\nAnalyze the pod failure.",
            chain_id="test-chain"
        )
    
    def create_test_available_tools(self) -> AvailableTools:
        """Create test AvailableTools for StageContext tests."""
        tool = MCPTool(
            server="k8s",
            name="get_pods",
            description="Get pod information"
        )
        return AvailableTools(tools=[tool])
    
    def create_mock_agent(self) -> Mock:
        """Create a mock BaseAgent for testing."""
        agent = Mock()
        agent.__class__.__name__ = "TestAgent"
        agent.mcp_servers.return_value = ["k8s-server", "aws-server"]
        return agent
    
    def test_stage_context_creation(self):
        """Test creating StageContext with all components."""
        chain_context = self.create_test_chain_context()
        available_tools = self.create_test_available_tools()
        agent = self.create_mock_agent()
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
        
        assert stage_context.chain_context == chain_context
        assert stage_context.available_tools == available_tools
        assert stage_context.agent == agent
    
    def test_stage_context_derived_properties(self):
        """Test StageContext derived properties."""
        chain_context = self.create_test_chain_context()
        available_tools = self.create_test_available_tools()
        agent = self.create_mock_agent()
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
        
        # Test property access
        assert stage_context.alert_data == {"pod": "test-pod", "namespace": "default"}
        assert stage_context.runbook_content == "# Test Runbook\nAnalyze the pod failure."
        assert stage_context.session_id == "test-session-123"
        assert stage_context.stage_name == "analysis"
        assert stage_context.agent_name == "TestAgent"
        assert stage_context.mcp_servers == ["k8s-server", "aws-server"]
    
    def test_stage_context_alert_data_is_copy(self):
        """Test that alert_data property returns a copy."""
        chain_context = self.create_test_chain_context()
        available_tools = self.create_test_available_tools()
        agent = self.create_mock_agent()
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
        
        alert_data = stage_context.alert_data
        alert_data["modified"] = "value"
        
        # Original data should not be modified
        assert "modified" not in chain_context.alert_data
    
    def test_stage_context_previous_stages_empty(self):
        """Test StageContext with no previous stages."""
        chain_context = self.create_test_chain_context()
        available_tools = self.create_test_available_tools()
        agent = self.create_mock_agent()
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
        
        assert stage_context.previous_stages_results == []
        assert not stage_context.has_previous_stages()
        assert stage_context.format_previous_stages_context() == "No previous stage context available."
    
    def test_stage_context_with_previous_stages(self):
        """Test StageContext with previous completed stages."""
        chain_context = self.create_test_chain_context()
        
        # Add completed previous stages
        result1 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataAgent",
            stage_description="Data Collection",
            timestamp_us=1234567890,
            result_summary="Collected system metrics and logs."
        )
        
        result2 = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="AnalysisAgent",
            stage_description="Initial Analysis",
            timestamp_us=1234567891,
            result_summary="Identified potential CPU bottleneck."
        )
        
        chain_context.add_stage_result("collection", result1)
        chain_context.add_stage_result("initial_analysis", result2)
        
        available_tools = self.create_test_available_tools()
        agent = self.create_mock_agent()
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
        
        # Test previous stages access
        previous = stage_context.previous_stages_results
        assert len(previous) == 2
        assert previous[0] == ("collection", result1)
        assert previous[1] == ("initial_analysis", result2)
        assert stage_context.has_previous_stages()
        
        # Test formatted context
        formatted = stage_context.format_previous_stages_context()
        assert "## Results from 'Data Collection' stage:" in formatted
        assert "Collected system metrics and logs." in formatted
        assert "## Results from 'Initial Analysis' stage:" in formatted
        assert "Identified potential CPU bottleneck." in formatted
    
    def test_stage_context_formatted_context_with_missing_description(self):
        """Test formatted context when stage_description is missing."""
        chain_context = self.create_test_chain_context()
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="UnnamedAgent",
            stage_description=None,  # Missing description
            timestamp_us=1234567890,
            result_summary="Stage completed successfully."
        )
        
        chain_context.add_stage_result("unnamed_stage", result)
        
        available_tools = self.create_test_available_tools()
        agent = self.create_mock_agent()
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        assert "## Results from 'unnamed_stage' stage:" in formatted
        assert "Stage completed successfully." in formatted


