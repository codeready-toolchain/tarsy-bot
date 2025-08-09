"""
Unit tests for Dashboard Hooks.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.hooks.dashboard_hooks import DashboardLLMHooks, DashboardMCPHooks


class TestDashboardLLMHooks:
    """Test DashboardLLMHooks functionality."""
    
    @pytest.fixture
    def mock_update_service(self):
        """Mock dashboard update service."""
        service = AsyncMock()
        service.process_llm_interaction = AsyncMock()
        return service
    
    @pytest.fixture
    def mock_dashboard_manager(self):
        """Mock WebSocket manager as fallback."""
        manager = AsyncMock()
        manager.broadcast_dashboard_update = AsyncMock()
        # Mock dashboard_manager with update_service
        dashboard_manager = Mock()
        dashboard_manager.update_service = None  # Will be set in tests
        manager.dashboard_manager = dashboard_manager
        manager.broadcast_session_update_advanced = AsyncMock(return_value=2)
        manager.broadcast_dashboard_update_advanced = AsyncMock(return_value=3)
        return manager
    
    @pytest.fixture
    def dashboard_hooks(self, mock_dashboard_manager, mock_update_service):
        """Create DashboardLLMHooks instance for testing."""
        return DashboardLLMHooks(
            dashboard_manager=mock_dashboard_manager,
            update_service=mock_update_service
        )
    
    @pytest.mark.unit
    def test_initialization(self, dashboard_hooks, mock_update_service, mock_dashboard_manager):
        """Test DashboardLLMHooks initialization."""
        assert dashboard_hooks.update_service == mock_update_service
        assert dashboard_hooks.dashboard_manager == mock_dashboard_manager
        
        # Test with only websocket manager
        hooks = DashboardLLMHooks(dashboard_manager=mock_dashboard_manager)
        assert hooks.update_service is None
        assert hooks.dashboard_manager == mock_dashboard_manager


class TestDashboardHooksContentTruncation:
    """Test content truncation logic for large responses."""
    
    @pytest.fixture
    def llm_hooks(self):
        """Create LLM hooks instance."""
        return DashboardLLMHooks(dashboard_manager=None)

    @pytest.fixture
    def mcp_hooks(self):
        """Create MCP hooks instance."""
        return DashboardMCPHooks(dashboard_manager=None)

    @pytest.mark.unit
    def test_prompt_preview_truncation_over_200_chars(self, llm_hooks):
        """Test prompt preview truncation for content over 200 characters."""
        long_prompt = "a" * 250  # 250 characters
        
        # Simulate the truncation logic from execute method
        prompt_preview = str(long_prompt)[:200] + "..." if len(str(long_prompt)) > 200 else str(long_prompt)
        
        assert len(prompt_preview) == 203  # 200 + "..."
        assert prompt_preview.endswith("...")
        assert prompt_preview.startswith("a" * 200)

    @pytest.mark.unit
    def test_prompt_preview_no_truncation_under_200_chars(self, llm_hooks):
        """Test prompt preview no truncation for content under 200 characters."""
        short_prompt = "a" * 150  # 150 characters
        
        # Simulate the truncation logic from execute method
        prompt_preview = str(short_prompt)[:200] + "..." if len(str(short_prompt)) > 200 else str(short_prompt)
        
        assert len(prompt_preview) == 150
        assert not prompt_preview.endswith("...")
        assert prompt_preview == short_prompt

    @pytest.mark.unit
    def test_response_preview_truncation_over_200_chars(self, llm_hooks):
        """Test response preview truncation for content over 200 characters."""
        long_response = "b" * 300  # 300 characters
        
        # Simulate the truncation logic from execute method
        response_preview = str(long_response)[:200] + "..." if len(str(long_response)) > 200 else str(long_response)
        
        assert len(response_preview) == 203  # 200 + "..."
        assert response_preview.endswith("...")
        assert response_preview.startswith("b" * 200)

    @pytest.mark.unit
    def test_tool_result_preview_truncation_over_300_chars(self, mcp_hooks):
        """Test tool result preview truncation for content over 300 characters."""
        large_result = {"output": "c" * 400}  # Large result
        
        # Simulate the truncation logic from execute method
        result_str = str(large_result)
        tool_result_preview = result_str[:300] + "..." if len(result_str) > 300 else result_str
        
        assert len(tool_result_preview) == 303  # 300 + "..."
        assert tool_result_preview.endswith("...")

    @pytest.mark.unit
    def test_tool_result_preview_no_truncation_under_300_chars(self, mcp_hooks):
        """Test tool result preview no truncation for content under 300 characters."""
        small_result = {"output": "small data", "status": "success"}
        
        # Simulate the truncation logic from execute method
        result_str = str(small_result)
        tool_result_preview = result_str[:300] + "..." if len(result_str) > 300 else result_str
        
        assert len(tool_result_preview) < 300
        assert not tool_result_preview.endswith("...")
        assert tool_result_preview == str(small_result)


class TestDashboardLLMHooksExecution:
    """Test core LLM hook execution logic."""
    
    @pytest.fixture
    def mock_update_service(self):
        """Mock dashboard update service."""
        service = AsyncMock()
        service.process_llm_interaction = AsyncMock(return_value=3)
        return service
    
    @pytest.fixture
    def mock_dashboard_manager(self):
        """Mock WebSocket manager."""
        manager = AsyncMock()
        dashboard_manager = Mock()
        manager.dashboard_manager = dashboard_manager
        manager.broadcast_session_update_advanced = AsyncMock(return_value=2)
        manager.broadcast_dashboard_update_advanced = AsyncMock(return_value=3)
        return manager
    
    @pytest.fixture
    def llm_hooks_with_service(self, mock_dashboard_manager, mock_update_service):
        """Create LLM hooks with update service."""
        mock_dashboard_manager.update_service = mock_update_service
        return DashboardLLMHooks(
            dashboard_manager=mock_dashboard_manager,
            update_service=mock_update_service
        )
    
    @pytest.fixture
    def llm_hooks_without_service(self, mock_dashboard_manager):
        """Create LLM hooks without update service (fallback mode)."""
        mock_dashboard_manager.update_service = None
        return DashboardLLMHooks(dashboard_manager=mock_dashboard_manager)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_llm_success_with_update_service(self, llm_hooks_with_service, mock_update_service):
        """Test successful LLM interaction with update service."""
        event_data = {
            'session_id': 'test_session_123',
            'args': {
                'prompt': 'Test prompt for analysis',
                'model': 'gpt-4'
            },
            'result': {
                'content': 'Test response from LLM',
                'tool_calls': [{'name': 'kubectl', 'args': {}}]
            },
            'start_time': datetime.now(),
            'end_time': datetime.now(),
            'error': None
        }
        
        await llm_hooks_with_service.execute('llm.post', **event_data)
        
        # Verify update service was called
        mock_update_service.process_llm_interaction.assert_called_once()
        call_args = mock_update_service.process_llm_interaction.call_args
        
        # Extract positional and keyword arguments
        args, kwargs = call_args
        session_id, update_data = args
        
        assert session_id == 'test_session_123'
        assert update_data['interaction_type'] == 'llm'
        assert update_data['model_used'] == 'gpt-4'
        assert update_data['success'] is True
        assert 'step_description' in update_data
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_llm_error_with_update_service(self, llm_hooks_with_service, mock_update_service):
        """Test LLM error with update service."""
        error_msg = "Connection timeout to LLM service"
        event_data = {
            'session_id': 'test_session_456',
            'args': {'prompt': 'Test prompt', 'model': 'gpt-4'},
            'result': {},
            'error': Exception(error_msg),
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        await llm_hooks_with_service.execute('llm.error', **event_data)
        
        # Verify update service was called
        mock_update_service.process_llm_interaction.assert_called_once()
        call_args = mock_update_service.process_llm_interaction.call_args
        
        # Extract positional and keyword arguments
        args, kwargs = call_args
        session_id, update_data = args
        
        assert session_id == 'test_session_456'
        assert update_data['success'] is False
        assert update_data['error_message'] == error_msg
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_llm_fallback_to_websocket(self, llm_hooks_without_service, mock_dashboard_manager):
        """Test fallback when update_service is None."""
        event_data = {
            'session_id': 'test_session_789',
            'args': {'prompt': 'Test prompt', 'model': 'claude-3'},
            'result': {'content': 'Test response'},
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        await llm_hooks_without_service.execute('llm.post', **event_data)
        
        # Verify fallback to direct WebSocket broadcasting
        mock_dashboard_manager.broadcaster.broadcast_session_update.assert_called_once()
        mock_dashboard_manager.broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Check session update call
        session_call_args = mock_dashboard_manager.broadcaster.broadcast_session_update.call_args
        session_id, session_data = session_call_args[0]
        assert session_id == 'test_session_789'
        assert session_data['interaction_type'] == 'llm'
        assert session_data['model_used'] == 'claude-3'
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_non_post_error_events(self, llm_hooks_with_service, mock_update_service):
        """Test that pre-events and other events are ignored."""
        event_data = {'session_id': 'test_session', 'args': {}}
        
        # Test pre-event (should be ignored)
        await llm_hooks_with_service.execute('llm.pre', **event_data)
        mock_update_service.process_llm_interaction.assert_not_called()
        
        # Test random event (should be ignored)
        await llm_hooks_with_service.execute('llm.something', **event_data)
        mock_update_service.process_llm_interaction.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_missing_session_id(self, llm_hooks_with_service, mock_update_service):
        """Test that events without session_id are ignored."""
        event_data = {
            'args': {'prompt': 'Test prompt'},
            'result': {'content': 'Response'}
        }
        
        await llm_hooks_with_service.execute('llm.post', **event_data)
        
        # Should not call update service without session_id
        mock_update_service.process_llm_interaction.assert_not_called()


class TestDashboardMCPHooks:
    """Test DashboardMCPHooks functionality."""
    
    @pytest.fixture
    def mock_update_service(self):
        """Mock dashboard update service."""
        service = AsyncMock()
        service.process_mcp_interaction = AsyncMock()
        return service
    
    @pytest.fixture
    def mock_dashboard_manager(self):
        """Mock WebSocket manager as fallback."""
        manager = AsyncMock()
        manager.broadcast_dashboard_update = AsyncMock()
        # Mock dashboard_manager with update_service
        dashboard_manager = Mock()
        dashboard_manager.update_service = None  # Will be set in tests
        manager.dashboard_manager = dashboard_manager
        manager.broadcast_session_update_advanced = AsyncMock(return_value=2)
        manager.broadcast_dashboard_update_advanced = AsyncMock(return_value=3)
        return manager
    
    @pytest.fixture
    def dashboard_hooks(self, mock_dashboard_manager, mock_update_service):
        """Create DashboardMCPHooks instance for testing."""  
        return DashboardMCPHooks(
            dashboard_manager=mock_dashboard_manager,
            update_service=mock_update_service
        )
    
    @pytest.mark.unit
    def test_initialization(self, dashboard_hooks, mock_update_service, mock_dashboard_manager):
        """Test DashboardMCPHooks initialization."""
        assert dashboard_hooks.update_service == mock_update_service
        assert dashboard_hooks.dashboard_manager == mock_dashboard_manager


class TestDashboardMCPHooksExecution:
    """Test core MCP hook execution logic."""
    
    @pytest.fixture
    def mock_update_service(self):
        """Mock dashboard update service."""
        service = AsyncMock()
        service.process_mcp_communication = AsyncMock(return_value=2)
        return service
    
    @pytest.fixture
    def mock_dashboard_manager(self):
        """Mock WebSocket manager."""
        manager = AsyncMock()
        dashboard_manager = Mock()
        manager.dashboard_manager = dashboard_manager
        manager.broadcast_session_update_advanced = AsyncMock(return_value=2)
        manager.broadcast_dashboard_update_advanced = AsyncMock(return_value=3)
        return manager
    
    @pytest.fixture
    def mcp_hooks_with_service(self, mock_dashboard_manager, mock_update_service):
        """Create MCP hooks with update service."""
        mock_dashboard_manager.update_service = mock_update_service
        return DashboardMCPHooks(
            dashboard_manager=mock_dashboard_manager,
            update_service=mock_update_service
        )
    
    @pytest.fixture
    def mcp_hooks_without_service(self, mock_dashboard_manager):
        """Create MCP hooks without update service (fallback mode)."""
        mock_dashboard_manager.update_service = None
        return DashboardMCPHooks(dashboard_manager=mock_dashboard_manager)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_mcp_success_with_update_service(self, mcp_hooks_with_service, mock_update_service):
        """Test successful MCP communication with update service."""
        event_data = {
            'session_id': 'mcp_session_123',
            'method': 'call_tool',
            'args': {
                'server_name': 'kubernetes',
                'tool_name': 'kubectl',
                'tool_arguments': {'namespace': 'default', 'command': 'get pods'}
            },
            'result': {'output': 'pod1 Running\npod2 Pending'},
            'start_time': datetime.now(),
            'end_time': datetime.now(),
            'error': None
        }
        
        await mcp_hooks_with_service.execute('mcp.post', **event_data)
        
        # Verify update service was called
        mock_update_service.process_mcp_communication.assert_called_once()
        call_args = mock_update_service.process_mcp_communication.call_args
        
        # Extract positional and keyword arguments
        args, kwargs = call_args
        session_id, update_data = args
        
        assert session_id == 'mcp_session_123'
        assert update_data['interaction_type'] == 'mcp'
        assert update_data['server_name'] == 'kubernetes'
        assert update_data['tool_name'] == 'kubectl'
        assert update_data['success'] is True
        assert 'step_description' in update_data
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_mcp_error_with_update_service(self, mcp_hooks_with_service, mock_update_service):
        """Test MCP error with update service."""
        error_msg = "Tool execution failed: kubectl not found"
        event_data = {
            'session_id': 'mcp_session_456',
            'method': 'call_tool',
            'args': {'server_name': 'kubernetes', 'tool_name': 'kubectl'},
            'result': None,
            'error': Exception(error_msg),
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        await mcp_hooks_with_service.execute('mcp.error', **event_data)
        
        # Verify update service was called
        mock_update_service.process_mcp_communication.assert_called_once()
        call_args = mock_update_service.process_mcp_communication.call_args
        
        # Extract positional and keyword arguments
        args, kwargs = call_args
        session_id, update_data = args
        
        assert session_id == 'mcp_session_456'
        assert update_data['success'] is False
        assert update_data['error_message'] == error_msg
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_mcp_fallback_to_websocket(self, mcp_hooks_without_service, mock_dashboard_manager):
        """Test fallback when update_service is None."""
        event_data = {
            'session_id': 'mcp_session_789',
            'method': 'list_tools',
            'args': {'server_name': 'file_operations'},
            'result': {'tools': ['read_file', 'write_file']},
            'start_time': datetime.now(),
            'end_time': datetime.now()
        }
        
        await mcp_hooks_without_service.execute('mcp.post', **event_data)
        
        # Verify fallback to direct WebSocket broadcasting
        mock_dashboard_manager.broadcaster.broadcast_session_update.assert_called_once()
        mock_dashboard_manager.broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Check session update call
        session_call_args = mock_dashboard_manager.broadcaster.broadcast_session_update.call_args
        session_id, session_data = session_call_args[0]
        assert session_id == 'mcp_session_789'
        assert session_data['interaction_type'] == 'mcp'
        assert session_data['server_name'] == 'file_operations'
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_non_post_error_events(self, mcp_hooks_with_service, mock_update_service):
        """Test that pre-events and other events are ignored."""
        event_data = {'session_id': 'test_session', 'args': {}}
        
        # Test pre-event (should be ignored)
        await mcp_hooks_with_service.execute('mcp.pre', **event_data)
        mock_update_service.process_mcp_communication.assert_not_called()
        
        # Test random event (should be ignored)
        await mcp_hooks_with_service.execute('mcp.something', **event_data)
        mock_update_service.process_mcp_communication.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_execute_ignores_missing_session_id(self, mcp_hooks_with_service, mock_update_service):
        """Test that events without session_id are ignored."""
        event_data = {
            'method': 'call_tool',
            'args': {'server_name': 'test', 'tool_name': 'test_tool'},
            'result': {'success': True}
        }
        
        await mcp_hooks_with_service.execute('mcp.post', **event_data)
        
        # Should not call update service without session_id
        mock_update_service.process_mcp_communication.assert_not_called()


class TestHookRegistration:
    """Test hook registration functions."""
    
    @pytest.mark.unit
    def test_register_dashboard_hooks_with_services(self):
        """Test registering dashboard hooks with both services."""
        mock_hook_manager = Mock()
        mock_update_service = AsyncMock()
        mock_dashboard_manager = AsyncMock()
        
        with patch('tarsy.hooks.dashboard_hooks.DashboardLLMHooks') as mock_llm_hooks_class:
            with patch('tarsy.hooks.dashboard_hooks.DashboardMCPHooks') as mock_mcp_hooks_class:
                with patch('tarsy.hooks.base_hooks.get_hook_manager', return_value=mock_hook_manager):
                    # Import and test the registration function
                    from tarsy.hooks.dashboard_hooks import register_dashboard_hooks
                    
                    mock_llm_hooks = Mock()
                    mock_mcp_hooks = Mock()
                    mock_llm_hooks_class.return_value = mock_llm_hooks
                    mock_mcp_hooks_class.return_value = mock_mcp_hooks
                    
                    register_dashboard_hooks(
                        dashboard_manager=mock_dashboard_manager
                    )
                    
                    # Verify hooks were created with correct parameters
                    mock_llm_hooks_class.assert_called_once_with(mock_dashboard_manager)
                    mock_mcp_hooks_class.assert_called_once_with(mock_dashboard_manager)
                    
                    # Verify hooks were registered
                    assert mock_hook_manager.register_hook.call_count == 4  # 2 LLM hooks + 2 MCP hooks
    
    @pytest.mark.unit
    def test_register_dashboard_hooks_websocket_only(self):
        """Test registering dashboard hooks with only WebSocket manager."""
        mock_hook_manager = Mock()
        mock_dashboard_manager = AsyncMock()
        
        with patch('tarsy.hooks.dashboard_hooks.DashboardLLMHooks') as mock_llm_hooks_class:
            with patch('tarsy.hooks.dashboard_hooks.DashboardMCPHooks') as mock_mcp_hooks_class:
                from tarsy.hooks.dashboard_hooks import register_dashboard_hooks
                
                register_dashboard_hooks(
                    dashboard_manager=mock_dashboard_manager
                )
                
                # Verify hooks were created with only WebSocket manager
                mock_llm_hooks_class.assert_called_once_with(mock_dashboard_manager)
                mock_mcp_hooks_class.assert_called_once_with(mock_dashboard_manager)
    
    @pytest.mark.unit
    def test_register_integrated_hooks(self):
        """Test registering integrated hooks with history system."""
        mock_hook_manager = Mock()
        mock_update_service = AsyncMock()
        mock_dashboard_manager = AsyncMock()
        
        # Mock the history hooks registration function
        with patch('tarsy.hooks.dashboard_hooks.register_history_hooks') as mock_register_history:
            with patch('tarsy.hooks.dashboard_hooks.register_dashboard_hooks') as mock_register_dashboard:
                from tarsy.hooks.dashboard_hooks import register_integrated_hooks
                
                register_integrated_hooks(mock_dashboard_manager)
                
                # Verify both registration functions were called
                mock_register_history.assert_called_once()
                mock_register_dashboard.assert_called_once_with(mock_dashboard_manager)


class TestHookErrorHandling:
    """Test error handling in dashboard hooks."""
    
    @pytest.fixture
    def mock_update_service(self):
        """Mock dashboard update service."""
        service = AsyncMock()
        return service
    
    @pytest.fixture
    def mock_dashboard_manager(self):
        """Mock WebSocket manager."""
        manager = AsyncMock()
        return manager
    
    @pytest.mark.unit
    def test_hooks_with_none_services(self):
        """Test hooks initialization with None services."""
        # Should not raise exception
        llm_hooks = DashboardLLMHooks(dashboard_manager=None)
        mcp_hooks = DashboardMCPHooks(dashboard_manager=None)
        
        assert llm_hooks.dashboard_manager is None
        assert mcp_hooks.dashboard_manager is None

if __name__ == "__main__":
    pytest.main([__file__]) 