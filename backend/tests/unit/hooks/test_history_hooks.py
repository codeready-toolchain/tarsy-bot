"""
Unit tests for History Hooks.

Tests the history hook functionality with mocked dependencies to ensure
proper data extraction, logging, and integration with history service.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from tarsy.hooks.history_hooks import LLMHooks, MCPHooks, register_history_hooks


class TestLLMHooks:
    """Test LLMHooks functionality."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock()
        service.log_llm_interaction = Mock(return_value=True)
        return service
    
    @pytest.fixture
    def llm_hooks(self, mock_history_service):
        """Create LLMHooks instance for testing."""
        with patch('tarsy.hooks.history_hooks.get_history_service', return_value=mock_history_service):
            return LLMHooks()
    
    @pytest.mark.unit
    def test_initialization(self, llm_hooks, mock_history_service):
        """Test LLMHooks initialization."""
        assert llm_hooks.name == "llm_history_hook"
        assert llm_hooks.history_service == mock_history_service
        assert llm_hooks.is_enabled is True


class TestLLMHooksExecution:
    """Test LLM hook execution logic and history service integration."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock()
        service.log_llm_interaction = Mock(return_value=True)
        return service
    
    @pytest.fixture
    def llm_hooks(self, mock_history_service):
        """Create LLM hooks with mocked history service."""
        with patch('tarsy.hooks.history_hooks.get_history_service', return_value=mock_history_service):
            return LLMHooks()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_successful_interaction(self, llm_hooks, mock_history_service):
        """Test successful LLM interaction execution and logging."""
        # Use Unix timestamps in microseconds
        from tarsy.models.history import now_us
        start_time_us = now_us()
        end_time_us = start_time_us + 1500000  # 1500ms later in microseconds
        
        event_data = {
            'session_id': 'test_session_123',
            'args': {
                'prompt': 'Test prompt for analysis',
                'model': 'gpt-4'
            },
            'result': {
                'content': 'Test response from LLM',
                'usage': {'prompt_tokens': 10, 'completion_tokens': 20}
            },
            'start_time_us': start_time_us,
            'end_time_us': end_time_us
        }
        
        with patch('tarsy.hooks.base_hooks.generate_step_description', return_value="LLM analysis using gpt-4"):
            await llm_hooks.execute('llm.post', **event_data)
        
        # Verify history service was called
        mock_history_service.log_llm_interaction.assert_called_once()
        call_args = mock_history_service.log_llm_interaction.call_args
        
        # Verify call arguments
        kwargs = call_args[1]
        assert kwargs['session_id'] == 'test_session_123'
        assert kwargs['model_used'] == 'gpt-4'
        assert kwargs['step_description'] == "LLM analysis using gpt-4"
        assert kwargs['prompt_text'] == 'Test prompt for analysis'
        assert kwargs['response_text'] == 'Test response from LLM'
        assert kwargs['token_usage'] == {'prompt_tokens': 10, 'completion_tokens': 20}
        assert kwargs['duration_ms'] == 1500

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_pre_events(self, llm_hooks, mock_history_service):
        """Test that pre-events are ignored."""
        event_data = {'session_id': 'test_session', 'args': {}}
        
        await llm_hooks.execute('llm.pre', **event_data)
        
        mock_history_service.log_llm_interaction.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_missing_session_id(self, llm_hooks, mock_history_service):
        """Test that events without session_id are ignored."""
        event_data = {
            'args': {'prompt': 'Test prompt'},
            'result': {'content': 'Response'}
        }
        
        await llm_hooks.execute('llm.post', **event_data)
        
        mock_history_service.log_llm_interaction.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_with_large_content_truncation(self, llm_hooks, mock_history_service):
        """Test that large content is truncated to 1000000 characters."""
        large_prompt = "a" * 50000  # 50k characters (within new limit)
        large_response = "b" * 40000  # 40k characters (within new limit)
        
        event_data = {
            'session_id': 'test_session_456',
            'args': {'prompt': large_prompt, 'model': 'gpt-3.5'},
            'result': {'content': large_response},
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        with patch('tarsy.hooks.base_hooks.generate_step_description', return_value="LLM processing using gpt-3.5"):
            await llm_hooks.execute('llm.post', **event_data)
        
        call_args = mock_history_service.log_llm_interaction.call_args[1]
        
        # Verify content is preserved (not truncated since within 1MB limit)
        assert len(call_args['prompt_text']) == 50000
        assert len(call_args['response_text']) == 40000
        assert call_args['prompt_text'] == large_prompt
        assert call_args['response_text'] == large_response


    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_history_service_failure(self, llm_hooks, mock_history_service):
        """Test handling of history service failure."""
        mock_history_service.log_llm_interaction.return_value = False
        
        event_data = {
            'session_id': 'test_session_fail',
            'args': {'prompt': 'Test prompt', 'model': 'gpt-4'},
            'result': {'content': 'Response'},
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        with patch('tarsy.hooks.base_hooks.generate_step_description', return_value="LLM processing using gpt-4"):
            # Should not raise exception despite service failure
            await llm_hooks.execute('llm.post', **event_data)
        
        mock_history_service.log_llm_interaction.assert_called_once()


class TestMCPHooks:
    """Test MCPHooks functionality."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock()
        service.log_mcp_communication = Mock(return_value=True)
        return service
    
    @pytest.fixture
    def mcp_hooks(self, mock_history_service):
        """Create MCPHooks instance for testing."""
        with patch('tarsy.hooks.history_hooks.get_history_service', return_value=mock_history_service):
            return MCPHooks()
    
    @pytest.mark.unit
    def test_initialization(self, mcp_hooks, mock_history_service):
        """Test MCPHooks initialization."""
        assert mcp_hooks.name == "mcp_history_hook"
        assert mcp_hooks.history_service == mock_history_service
        assert mcp_hooks.is_enabled is True


class TestMCPHooksExecution:
    """Test MCP hook execution logic and history service integration."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock()
        service.log_mcp_communication = Mock(return_value=True)
        return service
    
    @pytest.fixture
    def mcp_hooks(self, mock_history_service):
        """Create MCP hooks with mocked history service."""
        with patch('tarsy.hooks.history_hooks.get_history_service', return_value=mock_history_service):
            return MCPHooks()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_successful_tool_call(self, mcp_hooks, mock_history_service):
        """Test successful MCP tool call execution and logging."""
        # Use Unix timestamps in microseconds
        from tarsy.models.history import now_us
        start_time_us = now_us()
        end_time_us = start_time_us + 2500000  # 2500ms later in microseconds
        
        event_data = {
            'session_id': 'mcp_session_123',
            'method': 'call_tool',
            'args': {
                'server_name': 'kubernetes',
                'tool_name': 'kubectl-get-pods',
                'tool_arguments': {'namespace': 'default'}
            },
            'result': {'output': 'pod1 Running\npod2 Pending'},
            'start_time_us': start_time_us,
            'end_time_us': end_time_us
        }
        
        await mcp_hooks.execute('mcp.post', **event_data)
        
        # Verify history service was called
        mock_history_service.log_mcp_communication.assert_called_once()
        call_args = mock_history_service.log_mcp_communication.call_args[1]
        
        assert call_args['session_id'] == 'mcp_session_123'
        assert call_args['server_name'] == 'kubernetes'
        assert call_args['communication_type'] == 'tool_call'
        assert call_args['tool_name'] == 'kubectl-get-pods'
        assert call_args['tool_arguments'] == {'namespace': 'default'}
        assert call_args['tool_result'] == {'output': 'pod1 Running\npod2 Pending'}
        assert call_args['success'] is True
        assert call_args['duration_ms'] == 2500
        assert call_args['error_message'] is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_error_scenario(self, mcp_hooks, mock_history_service):
        """Test MCP error scenario execution and logging."""
        error_msg = "Tool execution failed: kubectl not found"
        event_data = {
            'session_id': 'mcp_session_error',
            'method': 'call_tool',
            'args': {'server_name': 'kubernetes', 'tool_name': 'kubectl'},
            'result': None,
            'error': Exception(error_msg),
            'start_time': datetime.now(),
            'end_time': datetime.now() + timedelta(milliseconds=500)
        }
        
        await mcp_hooks.execute('mcp.error', **event_data)
        
        call_args = mock_history_service.log_mcp_communication.call_args[1]
        
        assert call_args['success'] is False
        assert call_args['error_message'] == error_msg
        assert call_args['tool_result'] is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_tool_list_operation(self, mcp_hooks, mock_history_service):
        """Test tool list operation execution."""
        event_data = {
            'session_id': 'mcp_session_list',
            'method': 'list_tools',
            'args': {'server_name': 'filesystem'},
            'result': {
                'tools': [
                    {'name': 'read_file', 'description': 'Read file contents'},
                    {'name': 'write_file', 'description': 'Write file contents'}
                ]
            },
            'start_time': datetime.now(),
            'end_time': datetime.now() + timedelta(milliseconds=300)
        }
        
        await mcp_hooks.execute('mcp.post', **event_data)
        
        call_args = mock_history_service.log_mcp_communication.call_args[1]
        
        assert call_args['communication_type'] == 'tool_list'
        assert call_args['available_tools'] == event_data['result']
        assert call_args['tool_name'] is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_pre_events(self, mcp_hooks, mock_history_service):
        """Test that pre-events are ignored."""
        event_data = {'session_id': 'test_session', 'args': {}}
        
        await mcp_hooks.execute('mcp.pre', **event_data)
        
        mock_history_service.log_mcp_communication.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_missing_session_id(self, mcp_hooks, mock_history_service):
        """Test that events without session_id are ignored."""
        event_data = {
            'method': 'call_tool',
            'args': {'server_name': 'test', 'tool_name': 'test_tool'},
            'result': {'success': True}
        }
        
        await mcp_hooks.execute('mcp.post', **event_data)
        
        mock_history_service.log_mcp_communication.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_history_service_failure(self, mcp_hooks, mock_history_service):
        """Test handling of history service failure."""
        mock_history_service.log_mcp_communication.return_value = False
        
        event_data = {
            'session_id': 'mcp_session_fail',
            'method': 'call_tool',
            'args': {'server_name': 'test', 'tool_name': 'test_tool'},
            'result': {'status': 'success'},
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        # Should not raise exception despite service failure
        await mcp_hooks.execute('mcp.post', **event_data)
        
        mock_history_service.log_mcp_communication.assert_called_once()


class TestHistoryHookRegistration:
    """Test history hook registration functions."""
    
    @pytest.mark.unit
    def test_register_history_hooks(self):
        """Test registering history hooks with hook manager."""
        mock_hook_manager = Mock()
        
        with patch('tarsy.hooks.history_hooks.LLMHooks') as mock_llm_hooks_class:
            with patch('tarsy.hooks.history_hooks.MCPHooks') as mock_mcp_hooks_class:
                with patch('tarsy.hooks.base_hooks.get_hook_manager', return_value=mock_hook_manager):
                    mock_llm_hooks = Mock()
                    mock_mcp_hooks = Mock()
                    mock_llm_hooks_class.return_value = mock_llm_hooks
                    mock_mcp_hooks_class.return_value = mock_mcp_hooks
                    
                    result = register_history_hooks()
                    
                    # Verify hooks were created
                    mock_llm_hooks_class.assert_called_once()
                    mock_mcp_hooks_class.assert_called_once()
                    
                    # Verify hooks were registered
                    assert mock_hook_manager.register_hook.call_count == 4  # 2 LLM hooks + 2 MCP hooks
                    
                    # Verify return value
                    assert result == mock_hook_manager


if __name__ == "__main__":
    pytest.main([__file__]) 