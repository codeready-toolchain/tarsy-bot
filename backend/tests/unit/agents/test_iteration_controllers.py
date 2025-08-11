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
from tarsy.agents.constants import IterationStrategy


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
        assert "ReAct format" in system_message.content
        assert "Thought:" in system_message.content
        assert "Action:" in system_message.content
    
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
