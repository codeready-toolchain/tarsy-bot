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
from tarsy.agents.iteration_controllers.react_iteration_controller import SimpleReActController
from tarsy.agents.iteration_controllers.react_final_analysis_controller import ReactFinalAnalysisController
from tarsy.agents.iteration_controllers.react_stage_controller import ReactStageController
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


# Removed TestRegularIterationController - REGULAR strategy no longer supported


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
        builder.get_enhanced_react_system_message.return_value = "You are an AI assistant that analyzes alerts using the ReAct pattern."
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
        agent._compose_instructions.return_value = "Composed instructions with MCP server guidance"
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
        
        # Should return full ReAct history including final answer
        assert "Thought: Need to analyze the alert" in result
        assert "Final Answer: Analysis complete" in result
        
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
        
        # Should return full ReAct history including actions and final answer
        assert "Thought: Need to get more info" in result
        assert "Action: test-tool" in result
        assert "Observation: Tool executed successfully" in result 
        assert "Final Answer: Complete analysis" in result
        
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
        
        # Should return full ReAct history including error handling and final answer
        assert "Thought: Need to use tool" in result
        assert "Action: test-tool" in result
        assert "Observation: Error executing action" in result
        assert "Final Answer: Analysis with error" in result
        
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
        # Final analysis doesn't use enhanced ReAct system message anymore
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for final analysis testing."""
        agent = Mock()
        agent.create_prompt_context.return_value = Mock()
        agent.get_current_stage_execution_id.return_value = "stage-exec-123"
        agent._get_general_instructions.return_value = "## General SRE Agent Instructions\nYou are an expert SRE..."
        agent.custom_instructions.return_value = "Custom agent instructions here"
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
            agent=mock_agent
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
        assert call_args["mcp_data"] == {}  # Final analysis uses empty mcp_data
        assert call_args["available_tools"] is None
        assert call_args["stage_name"] == "final-analysis"
        assert call_args["is_final_stage"] is True
        assert call_args["previous_stages"] is None  # Handled by chain context
        assert call_args["stage_attributed_data"] is None  # Handled by chain context
        
        # Verify prompt building was called
        mock_prompt_builder.build_final_analysis_prompt.assert_called_once()
        
        # Verify LLM was called with correct messages
        mock_llm_client.generate_response.assert_called_once()
        call_args = mock_llm_client.generate_response.call_args[0]
        messages = call_args[0]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert "General SRE Agent Instructions" in messages[0].content
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
    async def test_execute_analysis_loop_with_previous_stage_data(self, controller, sample_context, mock_agent, mock_llm_client):
        """Test final analysis execution (previous stage data handled at chain level)."""        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Comprehensive final analysis complete"
        
        # Verify context creation was called correctly
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["mcp_data"] == {}  # Empty for final analysis
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_minimal_context(self, controller, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test final analysis with minimal context."""
        context = IterationContext(
            alert_data={"alert": "TestAlert"},
            runbook_content="Test runbook",
            available_tools=[],
            session_id="test-session-123",
            agent=mock_agent
        )
        
        result = await controller.execute_analysis_loop(context)
        
        assert result == "Comprehensive final analysis complete"
        
        # Verify context creation used correct parameters
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["mcp_data"] == {}  # Empty for final analysis
        assert call_args["previous_stages"] is None  # Handled by chain context
        assert call_args["stage_attributed_data"] is None  # Handled by chain context
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_llm_failure(self, controller, sample_context, mock_llm_client):
        """Test final analysis when LLM call fails."""
        mock_llm_client.generate_response.side_effect = Exception("LLM service unavailable")
        
        with pytest.raises(Exception, match="LLM service unavailable"):
            await controller.execute_analysis_loop(sample_context)


# Removed TestReactToolsController - REACT_TOOLS strategy no longer supported


@pytest.mark.unit
class TestReactStageController:
    """Test ReactStageController implementation."""
    
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
        builder.build_stage_analysis_react_prompt.return_value = "Stage analysis ReAct prompt"
        builder.get_enhanced_react_system_message.return_value = "You are an agent doing partial analysis using ReAct."
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
        agent._compose_instructions.return_value = "Composed instructions with MCP server guidance"
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_client, mock_prompt_builder):
        """Create ReactStageController instance."""
        return ReactStageController(mock_llm_client, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample iteration context for partial analysis testing."""
        return IterationContext(
            alert_data={"alert": "TestAlert", "severity": "high"},
            runbook_content="Test runbook content",
            available_tools=[{"name": "analysis-tool"}],
            session_id="test-session-789",
            agent=mock_agent,

        )
    
    def test_needs_mcp_tools(self, controller):
        """Test that ReactStageController needs MCP tools."""
        assert controller.needs_mcp_tools() is True
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success_immediate_completion(self, controller, sample_context, mock_agent, mock_llm_client, mock_prompt_builder):
        """Test successful partial analysis that completes immediately."""
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return full ReAct history for partial analysis
        assert "Thought: Need to analyze partially" in result
        assert "Final Answer: Partial analysis complete" in result
        
        # Verify agent context creation
        mock_agent.create_prompt_context.assert_called_once()
        call_args = mock_agent.create_prompt_context.call_args[1]
        assert call_args["stage_name"] == "partial-analysis"
        assert call_args["available_tools"] == {"tools": sample_context.available_tools}
        
        # Verify prompt building
        mock_prompt_builder.build_stage_analysis_react_prompt.assert_called_once()
        
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
        
        # Should return full ReAct history with tool execution for partial analysis
        assert "Thought: Need to analyze with tools" in result
        assert "Action: analysis-tool" in result
        assert "Observation: Tool executed successfully" in result
        assert "Final Answer: Comprehensive partial analysis" in result
        
        # Verify tool was executed
        mock_agent.execute_mcp_tools.assert_called_once()
        
        # Verify tool was executed during ReAct loop  
        mock_agent.execute_mcp_tools.assert_called_once()
        
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
    
    def test_create_react_stage_controller(self, mock_llm_client, mock_prompt_builder):
        """Test creating ReactStageController."""
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
                iteration_strategy=IterationStrategy.REACT_STAGE
            )
            
            assert isinstance(agent._iteration_controller, ReactStageController)
            assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
    
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
    
    def test_react_vs_react_stage_initialization(self, mock_dependencies):
        """Test that different strategies create different controllers."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"

        
        with patch('tarsy.agents.base_agent.get_prompt_builder', 
                   return_value=mock_dependencies['prompt_builder']):
            # Create agent with REACT strategy
            react_agent = TestAgent(
                llm_client=mock_dependencies['llm_client'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=IterationStrategy.REACT
            )
            
            # Create agent with REACT_STAGE strategy  
            react_stage_agent = TestAgent(
                llm_client=mock_dependencies['llm_client'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=IterationStrategy.REACT_STAGE
            )
            
            # Verify different controller types
            assert isinstance(react_agent._iteration_controller, SimpleReActController)
            assert isinstance(react_stage_agent._iteration_controller, ReactStageController)
            
            # Verify strategy property works correctly
            assert react_agent.iteration_strategy == IterationStrategy.REACT
            assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE


@pytest.mark.unit
class TestFinalAnswerExtraction:
    """Test final answer extraction from ReAct responses."""
    
    def test_multiline_final_answer_extraction(self):
        """Test extraction of multi-line Final Answer content."""
        # Create controller for testing (using SimpleReActController which has _extract_react_final_analysis)
        controller = SimpleReActController(Mock(), Mock())
        
        # Test response with multi-line Final Answer
        test_response = """Thought: I have gathered sufficient information.

Final Answer: ### Analysis Report: Test Alert

#### 1. Root Cause Analysis
The issue is caused by a stuck finalizer.

#### 2. Current System State  
- Namespace: test-namespace
- Status: Terminating

#### 3. Remediation Steps
1. Check operator status
2. Remove finalizer if safe

#### 4. Prevention Recommendations
- Monitor operator health
- Implement cleanup policies"""
        
        result = controller._extract_react_final_analysis(
            analysis_result=test_response,
            completion_patterns=["Analysis completed"],
            incomplete_patterns=["Analysis incomplete:"],
            fallback_extractor=None,
            fallback_message="No analysis found"
        )
        
        # Verify the full content was extracted
        assert "### Analysis Report: Test Alert" in result
        assert "#### 1. Root Cause Analysis" in result
        assert "The issue is caused by a stuck finalizer." in result
        assert "#### 2. Current System State" in result
        assert "#### 3. Remediation Steps" in result
        assert "#### 4. Prevention Recommendations" in result
        assert "- Monitor operator health" in result
        
        # Verify proper structure preservation
        lines = result.split('\n')
        assert len(lines) >= 10  # Should have multiple lines
        
    def test_single_line_final_answer_extraction(self):
        """Test extraction of single-line Final Answer content."""
        controller = SimpleReActController(Mock(), Mock())
        
        test_response = """Thought: Analysis complete.
Final Answer: Simple analysis result."""
        
        result = controller._extract_react_final_analysis(
            analysis_result=test_response,
            completion_patterns=["Analysis completed"],
            incomplete_patterns=["Analysis incomplete:"],
            fallback_extractor=None,
            fallback_message="No analysis found"
        )
        
        assert result == "Simple analysis result."
        
    def test_final_answer_with_subsequent_sections(self):
        """Test that extraction stops at next ReAct section."""
        controller = SimpleReActController(Mock(), Mock())
        
        test_response = """Final Answer: This is the analysis result.
This continues the analysis.

Thought: This should not be included.
Action: some-action"""
        
        result = controller._extract_react_final_analysis(
            analysis_result=test_response,
            completion_patterns=["Analysis completed"],
            incomplete_patterns=["Analysis incomplete:"],
            fallback_extractor=None,
            fallback_message="No analysis found"
        )
        
        assert result == "This is the analysis result.\nThis continues the analysis."
        assert "This should not be included" not in result
        assert "Action: some-action" not in result
