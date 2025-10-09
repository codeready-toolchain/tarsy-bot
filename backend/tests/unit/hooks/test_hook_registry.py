"""
Tests for typed hook registry functionality.

Tests the HookRegistry that manages initialization and registration
of typed hooks with dependency injection.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.hooks.hook_registry import HookRegistry, get_hook_registry


@pytest.mark.unit
class TestHookRegistry:
    """Test HookRegistry functionality."""
    
    @pytest.fixture
    def mock_typed_hook_manager(self):
        """Mock typed hook manager."""
        manager = Mock()
        manager.register_llm_hook = Mock()
        manager.register_mcp_hook = Mock()
        manager.register_mcp_list_hook = Mock()
        return manager
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        return Mock()
    
    @patch('tarsy.hooks.hook_registry.get_hook_manager')
    def test_initialization(self, mock_get_manager, mock_typed_hook_manager):
        """Test HookRegistry initialization."""
        mock_get_manager.return_value = mock_typed_hook_manager
        
        registry = HookRegistry()
        
        assert registry.typed_hook_manager == mock_typed_hook_manager
        assert registry._initialized is False
        mock_get_manager.assert_called_once()
    
    @patch('tarsy.hooks.hook_registry.get_hook_manager')
    @patch('tarsy.hooks.hook_registry.LLMHistoryHook')
    @patch('tarsy.hooks.hook_registry.MCPHistoryHook')
    @patch('tarsy.hooks.hook_registry.MCPListHistoryHook')
    @patch('tarsy.hooks.hook_registry.LLMEventHook')
    @patch('tarsy.hooks.hook_registry.MCPEventHook')
    @patch('tarsy.hooks.hook_registry.MCPListEventHook')
    @pytest.mark.asyncio
    async def test_initialize_hooks_success(self, mock_mcp_list_dash, mock_mcp_dash, mock_llm_dash,
                                          mock_mcp_list_hist, mock_mcp_hist, mock_llm_hist,
                                          mock_get_manager, mock_typed_hook_manager,
                                          mock_history_service):
        """Test successful hook initialization."""
        mock_get_manager.return_value = mock_typed_hook_manager
        
        # Create mock hook instances
        mock_llm_hist_instance = Mock()
        mock_mcp_hist_instance = Mock()
        mock_mcp_list_hist_instance = Mock()
        mock_llm_dash_instance = Mock()
        mock_mcp_dash_instance = Mock()
        mock_mcp_list_dash_instance = Mock()
        
        mock_llm_hist.return_value = mock_llm_hist_instance
        mock_mcp_hist.return_value = mock_mcp_hist_instance
        mock_mcp_list_hist.return_value = mock_mcp_list_hist_instance
        mock_llm_dash.return_value = mock_llm_dash_instance
        mock_mcp_dash.return_value = mock_mcp_dash_instance
        mock_mcp_list_dash.return_value = mock_mcp_list_dash_instance
        
        registry = HookRegistry()
        
        await registry.initialize_hooks(mock_history_service)
        
        # Verify hooks were created with correct services
        mock_llm_hist.assert_called_once_with(mock_history_service)
        mock_mcp_hist.assert_called_once_with(mock_history_service)
        mock_mcp_list_hist.assert_called_once_with(mock_history_service)
        # Event hooks no longer require dashboard_broadcaster
        mock_llm_dash.assert_called_once_with()
        mock_mcp_dash.assert_called_once_with()
        mock_mcp_list_dash.assert_called_once_with()
        
        # Verify hooks were registered
        expected_llm_calls = [
            (mock_llm_hist_instance,),
            (mock_llm_dash_instance,)
        ]
        expected_mcp_calls = [
            (mock_mcp_hist_instance,),
            (mock_mcp_dash_instance,)
        ]
        expected_mcp_list_calls = [
            (mock_mcp_list_hist_instance,),
            (mock_mcp_list_dash_instance,)
        ]
        
        assert mock_typed_hook_manager.register_llm_hook.call_count == 2
        assert mock_typed_hook_manager.register_mcp_hook.call_count == 2
        assert mock_typed_hook_manager.register_mcp_list_hook.call_count == 2
        
        assert registry._initialized is True
    
    @patch('tarsy.hooks.hook_registry.get_hook_manager')
    @pytest.mark.asyncio
    async def test_initialize_hooks_already_initialized(self, mock_get_manager, mock_typed_hook_manager,
                                                       mock_history_service):
        """Test initialization when already initialized."""
        mock_get_manager.return_value = mock_typed_hook_manager
        
        registry = HookRegistry()
        registry._initialized = True
        
        await registry.initialize_hooks(mock_history_service)
        
        # Should not register any hooks
        mock_typed_hook_manager.register_llm_hook.assert_not_called()
        mock_typed_hook_manager.register_mcp_hook.assert_not_called()
        mock_typed_hook_manager.register_mcp_list_hook.assert_not_called()
    
    @patch('tarsy.hooks.hook_registry.get_hook_manager')
    @patch('tarsy.hooks.hook_registry.LLMHistoryHook')
    @pytest.mark.asyncio
    async def test_initialize_hooks_with_error(self, mock_llm_hist, mock_get_manager, mock_typed_hook_manager,
                                             mock_history_service):
        """Test initialization with error."""
        mock_get_manager.return_value = mock_typed_hook_manager
        mock_llm_hist.side_effect = Exception("Hook creation failed")
        
        registry = HookRegistry()
        
        with pytest.raises(Exception, match="Hook creation failed"):
            await registry.initialize_hooks(mock_history_service)
        
        assert registry._initialized is False
    
    @patch('tarsy.hooks.hook_registry.get_hook_manager')
    def test_is_initialized(self, mock_get_manager, mock_typed_hook_manager):
        """Test is_initialized method."""
        mock_get_manager.return_value = mock_typed_hook_manager
        
        registry = HookRegistry()
        
        assert registry.is_initialized() is False
        
        registry._initialized = True
        assert registry.is_initialized() is True


@pytest.mark.unit
class TestHookRegistryFactory:
    """Test typed hook registry factory function."""
    
    def test_get_hook_registry(self):
        """Test get_hook_registry factory function."""
        registry = get_hook_registry()
        assert isinstance(registry, HookRegistry)
        
        # Should return same instance (singleton behavior)
        registry2 = get_hook_registry()
        assert registry is registry2