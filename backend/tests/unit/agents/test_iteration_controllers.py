"""
Unit tests for iteration controllers.

Tests the different iteration strategy implementations to ensure they behave correctly
and provide the expected processing patterns for agent execution.
"""

from unittest.mock import AsyncMock, Mock, patch
import pytest

from tarsy.agents.iteration_controllers.base_iteration_controller import (
    IterationContext,
)
from tarsy.agents.iteration_controllers.regular_iteration_controller import RegularIterationController
from tarsy.agents.iteration_controllers.react_iteration_controller import SimpleReActController
from tarsy.agents.iteration_controllers.react_final_analysis_controller import ReactFinalAnalysisController
from tarsy.agents.iteration_controllers.react_tools_controller import ReactToolsController
from tarsy.agents.iteration_controllers.react_tools_partial_controller import ReactToolsPartialController
from tarsy.models.constants import IterationStrategy


@pytest.mark.unit
class TestIterationContext:
    """Test IterationContext dataclass functionality."""
    
    def test_iteration_context_creation(self):
        """Test creating iteration context with required fields."""
        context = IterationContext(
            alert_data={"alert": "test"},
            runbook_content="test runbook",
            available_tools=[{"name": "test-tool"}],
            session_id="test-session-123"
        )
        
        assert context.alert_data == {"alert": "test"}
        assert context.runbook_content == "test runbook"
        assert context.available_tools == [{"name": "test-tool"}]
        assert context.session_id == "test-session-123"
        assert context.agent is None  # Default value
    
    def test_iteration_context_with_agent(self):
        """Test creating iteration context with agent reference."""
        mock_agent = Mock()
        context = IterationContext(
            alert_data={"alert": "test"},
            runbook_content="test runbook",
            available_tools=[],
            session_id="test-session-123",
            agent=mock_agent
        )
        
        assert context.agent == mock_agent


@pytest.mark.unit
class TestRegularIterationController:
    """Test RegularIterationController implementation."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for testing."""
        agent = Mock()
        agent.determine_mcp_tools = AsyncMock(return_value=[
            {
                "server": "test-server",
                "tool": "test-tool",
                "parameters": {"param": "value"},
                "reason": "test reason"
            }
        ])
        agent.execute_mcp_tools = AsyncMock(return_value={
            "test-server": [{"tool": "test-tool", "result": "success"}]
        })
        agent.analyze_alert = AsyncMock(return_value="Regular analysis complete")
        agent.max_iterations = 3
        return agent
    
    @pytest.fixture
    def controller(self):
        """Create RegularIterationController instance."""
        return RegularIterationController()
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample iteration context."""
        return IterationContext(
            alert_data={"alert": "TestAlert", "severity": "high"},
            runbook_content="Test runbook content",
            available_tools=[{"name": "test-tool", "description": "Test tool"}],
            session_id="test-session-123",
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success(self, controller, sample_context, mock_agent):
        """Test successful regular iteration analysis loop."""
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Regular analysis complete"
        
        # Verify the flow was followed correctly
        mock_agent.determine_mcp_tools.assert_called_once()
        mock_agent.execute_mcp_tools.assert_called()
        mock_agent.analyze_alert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test analysis loop with missing agent reference."""
        context = IterationContext(
            alert_data={},
            runbook_content="",
            available_tools=[],
            session_id="test-session-123",
            agent=None
        )
        
        with pytest.raises(ValueError, match="Agent reference is required in context"):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_tool_selection_failure(self, controller, sample_context, mock_agent):
        """Test analysis loop when tool selection fails."""
        # Mock tool selection to fail
        mock_agent.determine_mcp_tools.side_effect = Exception("Tool selection failed")
        
        await controller.execute_analysis_loop(sample_context)
        
        # Should still return analysis result with error info
        mock_agent.analyze_alert.assert_called_once()
        call_args = mock_agent.analyze_alert.call_args[0]
        assert "tool_selection_error" in call_args[2]  # mcp_data parameter
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_empty_tools(self, controller, sample_context, mock_agent):
        """Test analysis loop with no tools selected."""
        mock_agent.determine_mcp_tools.return_value = []
        mock_agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Regular analysis complete"
        # Should still execute analysis even with no tools
        mock_agent.analyze_alert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_continue_true_empty_tools(self, controller, sample_context, mock_agent):
        """Test analysis loop when determine_next_mcp_tools returns continue=true with empty tools."""
        # Mock determine_next_mcp_tools to return continue=true with empty tools list
        mock_agent.determine_next_mcp_tools = AsyncMock(return_value={
            "continue": True,
            "tools": []
        })
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Regular analysis complete"
        
        # Verify the sequence of calls
        mock_agent.determine_mcp_tools.assert_called_once()  # Initial tool selection
        mock_agent.execute_mcp_tools.assert_called_once()  # Initial tool execution
        mock_agent.determine_next_mcp_tools.assert_called_once()  # Next iteration check
        mock_agent.analyze_alert.assert_called_once()  # Final analysis
        
        # Verify that no additional tools were executed (only initial ones)
        assert mock_agent.execute_mcp_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_continue_false_early_return(self, controller, sample_context, mock_agent):
        """Test analysis loop when determine_next_mcp_tools returns continue=false for early exit."""
        # Mock determine_next_mcp_tools to return continue=false
        mock_agent.determine_next_mcp_tools = AsyncMock(return_value={
            "continue": False,
            "reason": "Sufficient data gathered"
        })
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Regular analysis complete"
        
        # Verify the sequence of calls
        mock_agent.determine_mcp_tools.assert_called_once()  # Initial tool selection
        mock_agent.execute_mcp_tools.assert_called_once()  # Initial tool execution
        mock_agent.determine_next_mcp_tools.assert_called_once()  # Next iteration check
        mock_agent.analyze_alert.assert_called_once()  # Final analysis
        
        # Verify that no additional tools were executed (only initial ones)
        assert mock_agent.execute_mcp_tools.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_analysis_loop_tool_execution_failure(self, controller, sample_context, mock_agent):
        """Test analysis loop when tool execution fails."""
        mock_agent.execute_mcp_tools.side_effect = Exception("Tool execution failed")
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should still return analysis result with error info
        assert result == "Regular analysis complete"
        mock_agent.analyze_alert.assert_called_once()
        call_args = mock_agent.analyze_alert.call_args[0]
        assert "tool_execution_error" in call_args[2]  # mcp_data parameter

    @pytest.mark.asyncio
    async def test_execute_analysis_loop_multiple_iterations(self, controller, sample_context, mock_agent):
        """Test analysis loop with multiple iterations."""
        call_count = 0
        
        def mock_determine_next_tools(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "continue": True,
                    "tools": [{"server": "test", "tool": "additional_tool", "parameters": {}}]
                }
            else:
                return {"continue": False}
        
        mock_agent.determine_next_mcp_tools = AsyncMock(side_effect=mock_determine_next_tools)
        mock_agent.merge_mcp_data = Mock(return_value={"merged": "data"})
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Regular analysis complete"
        assert mock_agent.execute_mcp_tools.call_count == 2  # Initial + 1 iteration
        mock_agent.merge_mcp_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_reached(self, controller, sample_context, mock_agent):
        """Test analysis loop reaching max iterations."""
        mock_agent.max_iterations = 2
        mock_agent.determine_next_mcp_tools = AsyncMock(return_value={
            "continue": True,
            "tools": [{"server": "test", "tool": "tool", "parameters": {}}]
        })
        mock_agent.merge_mcp_data = Mock(return_value={"merged": "data"})
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Regular analysis complete"
        # Should stop after max_iterations (initial + 2 iterations)
        assert mock_agent.execute_mcp_tools.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_analysis_loop_iteration_failure(self, controller, sample_context, mock_agent):
        """Test analysis loop when iteration fails."""
        mock_agent.determine_next_mcp_tools = AsyncMock(side_effect=Exception("Iteration failed"))
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should continue with analysis despite iteration failure
        assert result == "Regular analysis complete"
        mock_agent.analyze_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_analysis_loop_invalid_next_action_type(self, controller, sample_context, mock_agent):
        """Test analysis loop when determine_next_mcp_tools returns invalid type."""
        mock_agent.determine_next_mcp_tools = AsyncMock(return_value="invalid_type")
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should handle invalid type gracefully
        assert result == "Regular analysis complete"
        mock_agent.analyze_alert.assert_called_once()


@pytest.mark.unit
class TestSimpleReActController:
    """Test SimpleReActController implementation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock()
        client.generate_response = AsyncMock(return_value="Final Answer: Analysis complete")
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_standard_react_prompt.return_value = "ReAct prompt"
        builder.get_standard_react_system_message.return_value = "You are an AI assistant that analyzes alerts using the ReAct pattern."
        builder.parse_react_response.return_value = {
            'thought': 'Need to analyze the alert',
            'action': 'test-tool',
            'action_input': 'param=value',
            'is_complete': True,
            'final_answer': 'Analysis complete'
        }
        builder.convert_action_to_tool_call.return_value = {
            "server": "test-server",
            "tool": "test-tool",
            "parameters": {"param": "value"},
            "reason": "test"
        }
        builder.format_observation.return_value = "Tool executed successfully"
        builder.get_react_error_continuation.return_value = ["Error occurred, continuing analysis..."]
        builder._flatten_react_history.return_value = ["Thought: Analysis needed", "Action: test-tool", "Observation: Tool executed successfully"]
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for ReAct testing."""
        agent = Mock()
        agent.max_iterations = 3
        agent.create_prompt_context.return_value = Mock()
        agent.execute_mcp_tools = AsyncMock(return_value={
            "test-server": [{"tool": "test-tool", "result": "success"}]
        })
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_client, mock_prompt_builder):
        """Create SimpleReActController instance."""
        return SimpleReActController(mock_llm_client, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample iteration context for ReAct testing."""
        return IterationContext(
            alert_data={"alert": "TestAlert", "severity": "high"},
            runbook_content="Test runbook content",
            available_tools=[{"name": "test-tool"}],
            session_id="test-session-123",
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success(self, controller, sample_context, mock_llm_client):
        """Test successful ReAct analysis loop with final answer."""
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Analysis complete"
        
        # Verify LLM was called
        mock_llm_client.generate_response.assert_called()
        
        # Verify system message contains ReAct instructions
        call_args = mock_llm_client.generate_response.call_args[0][0]
        system_message = call_args[0]
        assert "ReAct" in system_message.content
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test ReAct analysis loop with missing agent reference."""
        context = IterationContext(
            alert_data={},
            runbook_content="",
            available_tools=[],
            session_id="test-session-123",
            agent=None
        )
        
        with pytest.raises(ValueError, match="Agent reference is required in context"):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_action_execution(
        self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder
    ):
        """Test ReAct loop that executes an action before completing."""
        # First response: action to execute
        mock_prompt_builder.parse_react_response.side_effect = [
            {
                'thought': 'Need to get more info',
                'action': 'test-tool',
                'action_input': 'param=value',
                'is_complete': False,
                'final_answer': None
            },
            {
                'thought': 'Now I have enough info',
                'action': None,
                'action_input': None,
                'is_complete': True,
                'final_answer': 'Complete analysis'
            }
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Complete analysis"
        
        # Verify tool was executed
        mock_agent.execute_mcp_tools.assert_called_once()
        
        # Verify multiple LLM calls for iterations
        assert mock_llm_client.generate_response.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_reached(
        self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder
    ):
        """Test ReAct loop that reaches maximum iterations."""
        mock_agent.max_iterations = 1  # Force max iterations quickly
        
        # Always return incomplete response to force max iterations
        mock_prompt_builder.parse_react_response.return_value = {
            'thought': 'Still thinking...',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        
        # Mock fallback response
        mock_llm_client.generate_response.return_value = "Fallback analysis"
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert "Analysis completed (reached max iterations)" in result
        assert "Fallback analysis" in result
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_tool_execution_error(
        self, controller, sample_context, mock_agent, mock_prompt_builder
    ):
        """Test ReAct loop with tool execution error."""
        # Mock tool execution to fail
        mock_agent.execute_mcp_tools.side_effect = Exception("Tool execution failed")
        
        # Return action first, then completion
        mock_prompt_builder.parse_react_response.side_effect = [
            {
                'thought': 'Need to use tool',
                'action': 'test-tool',
                'action_input': 'param=value',
                'is_complete': False,
                'final_answer': None
            },
            {
                'thought': 'Tool failed but continuing',
                'action': None,
                'action_input': None,
                'is_complete': True,
                'final_answer': 'Analysis with error'
            }
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Analysis with error"
        
        # Verify tool execution was attempted
        mock_agent.execute_mcp_tools.assert_called_once()


@pytest.mark.unit
class TestReactFinalAnalysisController:
    """Test ReactFinalAnalysisController implementation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock()
        client.generate_response = AsyncMock(return_value="Comprehensive final analysis complete")
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_final_analysis_prompt.return_value = "Final analysis prompt"
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for final analysis testing."""
        agent = Mock()
        agent.create_prompt_context.return_value = Mock()
        agent.get_current_stage_execution_id.return_value = "stage-exec-123"
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_client, mock_prompt_builder):
        """Create ReactFinalAnalysisController instance."""
        return ReactFinalAnalysisController(mock_llm_client, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample iteration context for final analysis testing."""
        return IterationContext(
            alert_data={"alert": "TestAlert", "severity": "high"},
            runbook_content="Test runbook content",
            available_tools=[{"name": "test-tool"}],
            session_id="test-session-123",
            agent=mock_agent,
            initial_mcp_data={"server1": [{"tool": "tool1", "data": "test_data"}]},
            stage_attributed_data={"stage1": {"key": "value"}}
        )
    
    def test_needs_mcp_tools(self, controller):
        """Test that ReactFinalAnalysisController doesn't need MCP tools."""
        assert controller.needs_mcp_tools() is False
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test successful final analysis execution."""
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Comprehensive final analysis complete"
        
        # Verify agent context creation was called properly
        mock_agent.create_prompt_context.assert_called_once()
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["alert_data"] == sample_context.alert_data
        assert call_args["runbook_content"] == sample_context.runbook_content
        assert call_args["mcp_data"] == sample_context.initial_mcp_data
        assert call_args["available_tools"] is None
        assert call_args["stage_name"] == "final-analysis"
        assert call_args["is_final_stage"] is True
        assert call_args["previous_stages"] == ["stage1"]
        assert call_args["stage_attributed_data"] == sample_context.stage_attributed_data
        
        # Verify prompt building was called
        mock_prompt_builder.build_final_analysis_prompt.assert_called_once()
        
        # Verify LLM was called with correct messages
        mock_llm_client.generate_response.assert_called_once()
        call_args = mock_llm_client.generate_response.call_args[0]
        messages = call_args[0]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert "expert SRE" in messages[0].content
        assert messages[1].role == "user"
        assert messages[1].content == "Final analysis prompt"
        
        # Verify session_id and stage execution id passed correctly
        assert call_args[1] == sample_context.session_id
        assert call_args[2] == "stage-exec-123"
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test final analysis loop with missing agent reference."""
        context = IterationContext(
            alert_data={},
            runbook_content="",
            available_tools=[],
            session_id="test-session-123",
            agent=None
        )
        
        # Should not raise error, agent is used but validated internally
        with pytest.raises(AttributeError):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_initial_mcp_data(self, controller, sample_context, mock_agent, mock_llm_client):
        """Test final analysis with accumulated MCP data from previous stages."""
        # Mock additional data sources
        sample_context.initial_mcp_data = {
            "server1": [{"tool": "tool1", "data": "data1"}],
            "server2": [{"tool": "tool2", "data": "data2"}]
        }
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Comprehensive final analysis complete"
        
        # Verify context creation included all MCP data
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["mcp_data"] == sample_context.initial_mcp_data
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_without_initial_mcp_data(self, controller, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test final analysis without previous stage data."""
        context = IterationContext(
            alert_data={"alert": "TestAlert"},
            runbook_content="Test runbook",
            available_tools=[],
            session_id="test-session-123",
            agent=mock_agent,
            initial_mcp_data=None,
            stage_attributed_data=None
        )
        
        result = await controller.execute_analysis_loop(context)
        
        assert result == "Comprehensive final analysis complete"
        
        # Verify context creation handled None values
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["mcp_data"] is None
        assert call_args["previous_stages"] is None
        assert call_args["stage_attributed_data"] is None
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_llm_failure(self, controller, sample_context, mock_llm_client):
        """Test final analysis when LLM call fails."""
        mock_llm_client.generate_response.side_effect = Exception("LLM service unavailable")
        
        with pytest.raises(Exception, match="LLM service unavailable"):
            await controller.execute_analysis_loop(sample_context)


@pytest.mark.unit  
class TestReactToolsController:
    """Test ReactToolsController implementation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock()
        client.generate_response = AsyncMock(return_value="Final Answer: Data collection complete")
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_data_collection_react_prompt.return_value = "Data collection ReAct prompt"
        builder.get_standard_react_system_message.return_value = "You are a data collection agent using ReAct."
        builder.parse_react_response.return_value = {
            'thought': 'Need to collect data',
            'action': 'test-tool',
            'action_input': 'param=value',
            'is_complete': True,
            'final_answer': 'Data collection complete'
        }
        builder.convert_action_to_tool_call.return_value = {
            "server": "test-server",
            "tool": "test-tool", 
            "parameters": {"param": "value"},
            "reason": "data collection"
        }
        builder.format_observation.return_value = "Tool executed successfully for data collection"
        builder.get_react_continuation_prompt.return_value = ["Please continue with data collection..."]
        builder.get_react_error_continuation.return_value = ["Error occurred, continue collecting data..."]
        builder._flatten_react_history.return_value = ["Thought: Need data", "Action: test-tool", "Observation: Data collected"]
        builder.truncate_conversation_history.return_value = ["Truncated history"]
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for data collection testing."""
        agent = Mock()
        agent.max_iterations = 3
        agent.create_prompt_context.return_value = Mock()
        agent.get_current_stage_execution_id.return_value = "stage-exec-456"
        agent.execute_mcp_tools = AsyncMock(return_value={
            "test-server": [{"tool": "test-tool", "result": "data collected"}]
        })
        agent.merge_mcp_data = Mock(return_value={"merged": "data"})
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_client, mock_prompt_builder):
        """Create ReactToolsController instance."""
        return ReactToolsController(mock_llm_client, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample iteration context for data collection testing."""
        return IterationContext(
            alert_data={"alert": "TestAlert", "severity": "high"},
            runbook_content="Test runbook content",
            available_tools=[{"name": "test-tool"}],
            session_id="test-session-456", 
            agent=mock_agent,
            initial_mcp_data={"server0": [{"tool": "initial", "data": "initial_data"}]},
            stage_attributed_data={"previous_stage": {"key": "value"}},
            final_mcp_data={}
        )
    
    def test_needs_mcp_tools(self, controller):
        """Test that ReactToolsController needs MCP tools."""
        assert controller.needs_mcp_tools() is True
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success_immediate_completion(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test successful data collection that completes immediately."""
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Data collection complete"
        
        # Verify agent context creation
        mock_agent.create_prompt_context.assert_called_once()
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["stage_name"] == "data-collection"
        assert call_args["available_tools"] == {"tools": sample_context.available_tools}
        
        # Verify prompt building
        mock_prompt_builder.build_data_collection_react_prompt.assert_called_once()
        
        # Verify LLM call
        mock_llm_client.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test data collection loop with missing agent reference."""
        context = IterationContext(
            alert_data={},
            runbook_content="",
            available_tools=[],
            session_id="test-session-123",
            agent=None
        )
        
        with pytest.raises(ValueError, match="Agent reference is required in context"):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_tool_execution(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test data collection loop that executes tools before completing."""
        # Mock sequence: action first, then completion
        mock_prompt_builder.parse_react_response.side_effect = [
            {
                'thought': 'Need to collect data',
                'action': 'test-tool',
                'action_input': 'param=value',
                'is_complete': False,
                'final_answer': None
            },
            {
                'thought': 'Data collected successfully',
                'action': None,
                'action_input': None,
                'is_complete': True,
                'final_answer': 'All data collected'
            }
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "All data collected"
        
        # Verify tool was executed
        mock_agent.execute_mcp_tools.assert_called_once()
        
        # Verify data merging
        mock_agent.merge_mcp_data.assert_called_once()
        
        # Verify observation formatting
        mock_prompt_builder.format_observation.assert_called_once()
        
        # Verify multiple LLM calls
        assert mock_llm_client.generate_response.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_tool_execution_error(self, controller, sample_context, mock_agent, mock_prompt_builder):
        """Test data collection loop with tool execution error."""
        # Mock tool execution failure
        mock_agent.execute_mcp_tools.side_effect = Exception("Tool execution failed")
        
        # Mock sequence: action fails, then completion
        mock_prompt_builder.parse_react_response.side_effect = [
            {
                'thought': 'Need to collect data',
                'action': 'test-tool',
                'action_input': 'param=value',
                'is_complete': False,
                'final_answer': None
            },
            {
                'thought': 'Tool failed but continuing',
                'action': None,
                'action_input': None,
                'is_complete': True,
                'final_answer': 'Data collection with errors'
            }
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Data collection with errors"
        
        # Verify tool execution was attempted
        mock_agent.execute_mcp_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_reached(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test data collection loop that reaches maximum iterations."""
        mock_agent.max_iterations = 1  # Force quick max iterations
        
        # Mock always incomplete response
        mock_prompt_builder.parse_react_response.return_value = {
            'thought': 'Still collecting data...',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        
        # Mock fallback response
        fallback_response = "Partial data collection summary"
        mock_llm_client.generate_response.side_effect = ["ReAct response", fallback_response]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert "Data collection completed (reached max iterations)" in result
        assert fallback_response in result
        
        # Should include fallback LLM call
        assert mock_llm_client.generate_response.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_missing_action_continuation(self, controller, sample_context, mock_agent, mock_prompt_builder):
        """Test data collection loop with missing action that needs continuation."""
        # Mock sequence: incomplete without action, then completion
        mock_prompt_builder.parse_react_response.side_effect = [
            {
                'thought': 'Thinking about data collection',
                'action': None,
                'action_input': None,
                'is_complete': False,
                'final_answer': None
            },
            {
                'thought': 'Now ready to complete',
                'action': None,
                'action_input': None,
                'is_complete': True,
                'final_answer': 'Data collection done'
            }
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Data collection done"
        
        # Verify continuation prompt was added
        mock_prompt_builder.get_react_continuation_prompt.assert_called_once_with("data_collection")
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_history_truncation(self, controller, sample_context, mock_agent, mock_prompt_builder):
        """Test data collection loop with conversation history truncation."""
        iteration_count = 0
        
        def side_effect_parse(response):
            nonlocal iteration_count
            iteration_count += 1
            
            # Complete after many iterations to trigger history truncation logic
            if iteration_count < 20:  # Keep adding to history
                return {
                    'thought': f'Adding to history iteration {iteration_count}',
                    'action': None,
                    'action_input': None,
                    'is_complete': False,
                    'final_answer': None
                }
            else:  # Finally complete
                return {
                    'thought': 'Final completion',
                    'action': None,
                    'action_input': None,
                    'is_complete': True,
                    'final_answer': 'Data collection complete'
                }
        
        # Set high max iterations to allow for history buildup
        mock_agent.max_iterations = 25
        mock_prompt_builder.parse_react_response.side_effect = side_effect_parse
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Data collection complete"
        
        # Verify truncation was called due to history length
        mock_prompt_builder.truncate_conversation_history.assert_called()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_iteration_exception(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test data collection loop with exception during iteration."""
        # Mock LLM to fail first, then succeed
        mock_llm_client.generate_response.side_effect = [
            Exception("Network error"),
            "Final Answer: Data collection recovered"
        ]
        
        mock_prompt_builder.parse_react_response.return_value = {
            'thought': 'Recovered from error',
            'action': None,
            'action_input': None,
            'is_complete': True,
            'final_answer': 'Data collection recovered'
        }
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Data collection recovered"
        
        # Verify error continuation was called
        mock_prompt_builder.get_react_error_continuation.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_fallback_generation_error(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test data collection loop with fallback generation failure."""
        mock_agent.max_iterations = 1
        
        # Mock incomplete response
        mock_prompt_builder.parse_react_response.return_value = {
            'thought': 'Still working',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        
        # Mock both initial and fallback LLM calls to fail
        mock_llm_client.generate_response.side_effect = [
            "Initial response",
            Exception("Fallback generation failed")
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert "Data collection incomplete" in result
        assert "reached maximum iterations" in result


@pytest.mark.unit
class TestReactToolsPartialController:
    """Test ReactToolsPartialController implementation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock()
        client.generate_response = AsyncMock(return_value="Final Answer: Partial analysis complete")
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_partial_analysis_react_prompt.return_value = "Partial analysis ReAct prompt"
        builder.get_standard_react_system_message.return_value = "You are an agent doing partial analysis using ReAct."
        builder.parse_react_response.return_value = {
            'thought': 'Need to analyze partially',
            'action': 'analysis-tool',
            'action_input': 'param=value',
            'is_complete': True,
            'final_answer': 'Partial analysis complete'
        }
        builder.convert_action_to_tool_call.return_value = {
            "server": "analysis-server",
            "tool": "analysis-tool",
            "parameters": {"param": "value"},
            "reason": "partial analysis"
        }
        builder.format_observation.return_value = "Tool executed successfully for analysis"
        builder.get_react_continuation_prompt.return_value = ["Please continue with analysis..."]
        builder.get_react_error_continuation.return_value = ["Error occurred, continue analysis..."]
        builder._flatten_react_history.return_value = ["Thought: Need analysis", "Action: analysis-tool", "Observation: Analysis done"]
        builder.truncate_conversation_history.return_value = ["Truncated analysis history"]
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for partial analysis testing."""
        agent = Mock()
        agent.max_iterations = 3
        agent.create_prompt_context.return_value = Mock()
        agent.get_current_stage_execution_id.return_value = "stage-exec-789"
        agent.execute_mcp_tools = AsyncMock(return_value={
            "analysis-server": [{"tool": "analysis-tool", "result": "analysis data"}]
        })
        agent.merge_mcp_data = Mock(return_value={"merged": "analysis_data"})
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_client, mock_prompt_builder):
        """Create ReactToolsPartialController instance."""
        return ReactToolsPartialController(mock_llm_client, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample iteration context for partial analysis testing."""
        return IterationContext(
            alert_data={"alert": "TestAlert", "severity": "high"},
            runbook_content="Test runbook content",
            available_tools=[{"name": "analysis-tool"}],
            session_id="test-session-789",
            agent=mock_agent,
            initial_mcp_data={"server0": [{"tool": "initial", "data": "initial_data"}]},
            stage_attributed_data={"previous_stage": {"key": "value"}},
            final_mcp_data={}
        )
    
    def test_needs_mcp_tools(self, controller):
        """Test that ReactToolsPartialController needs MCP tools."""
        assert controller.needs_mcp_tools() is True
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success_immediate_completion(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test successful partial analysis that completes immediately."""
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Partial analysis complete"
        
        # Verify agent context creation
        mock_agent.create_prompt_context.assert_called_once()
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["stage_name"] == "partial-analysis"
        assert call_args["available_tools"] == {"tools": sample_context.available_tools}
        
        # Verify prompt building
        mock_prompt_builder.build_partial_analysis_react_prompt.assert_called_once()
        
        # Verify LLM call
        mock_llm_client.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test partial analysis loop with missing agent reference."""
        context = IterationContext(
            alert_data={},
            runbook_content="",
            available_tools=[],
            session_id="test-session-123",
            agent=None
        )
        
        with pytest.raises(ValueError, match="Agent reference is required in context"):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_tool_execution(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test partial analysis loop that executes tools before completing."""
        # Mock sequence: action first, then completion
        mock_prompt_builder.parse_react_response.side_effect = [
            {
                'thought': 'Need to analyze with tools',
                'action': 'analysis-tool',
                'action_input': 'param=value',
                'is_complete': False,
                'final_answer': None
            },
            {
                'thought': 'Analysis completed successfully',
                'action': None,
                'action_input': None,
                'is_complete': True,
                'final_answer': 'Comprehensive partial analysis'
            }
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Comprehensive partial analysis"
        
        # Verify tool was executed
        mock_agent.execute_mcp_tools.assert_called_once()
        
        # Verify data merging
        mock_agent.merge_mcp_data.assert_called_once()
        
        # Verify observation formatting
        mock_prompt_builder.format_observation.assert_called_once()
        
        # Verify multiple LLM calls
        assert mock_llm_client.generate_response.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_with_fallback(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test partial analysis loop that reaches maximum iterations and generates fallback."""
        mock_agent.max_iterations = 1  # Force quick max iterations
        
        # Mock always incomplete response
        mock_prompt_builder.parse_react_response.return_value = {
            'thought': 'Still analyzing...',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        
        # Mock fallback response
        fallback_response = "Partial analysis summary based on available data"
        mock_llm_client.generate_response.side_effect = ["ReAct response", fallback_response]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert "Partial analysis completed (reached max iterations)" in result
        assert fallback_response in result
        
        # Should include fallback LLM call
        assert mock_llm_client.generate_response.call_count >= 2
        
        # Verify fallback prompt includes correct system message
        fallback_call_args = mock_llm_client.generate_response.call_args_list[1][0]
        fallback_messages = fallback_call_args[0]
        assert fallback_messages[0].role == "system"
        assert "stage-specific analysis" in fallback_messages[0].content
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_fallback_failure(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test partial analysis loop with fallback generation failure."""
        mock_agent.max_iterations = 1
        
        # Mock incomplete response
        mock_prompt_builder.parse_react_response.return_value = {
            'thought': 'Still working on analysis',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        
        # Mock both initial and fallback LLM calls, with fallback failing
        mock_llm_client.generate_response.side_effect = [
            "Initial response",
            Exception("Fallback analysis generation failed")
        ]
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert "Partial analysis incomplete" in result
        assert "reached maximum iterations" in result
        assert "without final answer" in result


@pytest.mark.unit
class TestIterationControllerFactory:
    """Test the factory method in BaseAgent for creating iteration controllers."""
    
    @pytest.fixture
    def mock_llm_client(self):
        return Mock()
    
    @pytest.fixture
    def mock_prompt_builder(self):
        return Mock()
    
    def test_create_regular_iteration_controller(self, mock_llm_client, mock_prompt_builder):
        """Test creating RegularIterationController."""
        from tarsy.agents.base_agent import BaseAgent
        
        # We can't instantiate BaseAgent directly, so we'll test the factory method logic
        # by importing and testing the method directly in a concrete test class
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', return_value=mock_prompt_builder):
            agent = TestAgent(
                llm_client=mock_llm_client,
                mcp_client=Mock(),
                mcp_registry=Mock(),
                iteration_strategy=IterationStrategy.REGULAR
            )
            
            assert isinstance(agent._iteration_controller, RegularIterationController)
            assert agent.iteration_strategy == IterationStrategy.REGULAR
    
    def test_create_react_iteration_controller(self, mock_llm_client, mock_prompt_builder):
        """Test creating SimpleReActController."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', return_value=mock_prompt_builder):
            agent = TestAgent(
                llm_client=mock_llm_client,
                mcp_client=Mock(),
                mcp_registry=Mock(),
                iteration_strategy=IterationStrategy.REACT
            )
            
            assert isinstance(agent._iteration_controller, SimpleReActController)
            assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_create_unknown_iteration_strategy_fails(self, mock_llm_client, mock_prompt_builder):
        """Test that unknown iteration strategy raises ValueError."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', return_value=mock_prompt_builder):
            with pytest.raises(ValueError, match="Unknown iteration strategy"):
                TestAgent(
                    llm_client=mock_llm_client,
                    mcp_client=Mock(),
                    mcp_registry=Mock(),
                    iteration_strategy="unknown_strategy"  # Invalid strategy
                )


@pytest.mark.unit
class TestIterationControllerIntegration:
    """Test interaction between different iteration controllers and agents."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create all mock dependencies."""
        return {
            'llm_client': Mock(),
            'mcp_client': Mock(),
            'mcp_registry': Mock(),
            'prompt_builder': Mock()
        }
    
    def test_regular_vs_react_initialization(self, mock_dependencies):
        """Test that different strategies create different controllers."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', 
                   return_value=mock_dependencies['prompt_builder']):
            # Create agent with REGULAR strategy
            regular_agent = TestAgent(
                llm_client=mock_dependencies['llm_client'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=IterationStrategy.REGULAR
            )
            
            # Create agent with REACT strategy  
            react_agent = TestAgent(
                llm_client=mock_dependencies['llm_client'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=IterationStrategy.REACT
            )
            
            # Verify different controller types
            assert isinstance(regular_agent._iteration_controller, RegularIterationController)
            assert isinstance(react_agent._iteration_controller, SimpleReActController)
            
            # Verify strategy property works correctly
            assert regular_agent.iteration_strategy == IterationStrategy.REGULAR
            assert react_agent.iteration_strategy == IterationStrategy.REACT
