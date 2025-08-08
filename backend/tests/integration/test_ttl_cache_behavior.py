"""
Integration tests for TTL cache behavior in AlertService.

Tests cache expiration, memory management, and performance characteristics
of the TTL-based caching system for alert IDs and session mappings.
"""

import time
import uuid
from unittest.mock import Mock, patch

import pytest
from cachetools import TTLCache

from tarsy.config.settings import Settings
from tarsy.services.alert_service import AlertService


@pytest.mark.integration
class TestTTLCacheBehavior:
    """Integration tests for TTL cache functionality in AlertService."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock(spec=Settings)
        settings.github_token = "test_token"
        settings.history_enabled = True
        return settings

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AlertService dependencies."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.AgentRegistry') as mock_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            yield {
                'runbook': mock_runbook.return_value,
                'history': mock_history.return_value,
                'registry': mock_registry.return_value,
                'mcp_registry': mock_mcp_registry.return_value,
                'mcp_client': mock_mcp_client.return_value,
                'llm_manager': mock_llm_manager.return_value
            }

    @pytest.fixture
    def alert_service_with_short_ttl(self, mock_settings, mock_dependencies):
        """Create AlertService with short TTL for testing expiration."""
        with patch('tarsy.services.alert_service.TTLCache') as mock_ttl_cache:
            # Create real TTL caches with short expiration for testing
            mock_ttl_cache.side_effect = lambda maxsize, ttl: TTLCache(maxsize=maxsize, ttl=1)  # 1 second TTL
            
            service = AlertService(mock_settings)
            return service

    def test_cache_initialization_parameters(self, mock_settings, mock_dependencies):
        """Test that caches are initialized with correct parameters."""
        service = AlertService(mock_settings)
        
        # Verify cache types and parameters
        assert isinstance(service.alert_session_mapping, TTLCache)
        assert isinstance(service.valid_alert_ids, TTLCache)
        
        assert service.alert_session_mapping.maxsize == 10000
        assert service.valid_alert_ids.maxsize == 10000
        assert service.alert_session_mapping.ttl == 4 * 3600  # 4 hours
        assert service.valid_alert_ids.ttl == 4 * 3600  # 4 hours

    def test_cache_expiration_behavior(self, alert_service_with_short_ttl):
        """Test that cache entries expire after TTL."""
        alert_id = "test-expiration-alert"
        session_id = "test-expiration-session"
        
        # Add entries to both caches
        alert_service_with_short_ttl.register_alert_id(alert_id)
        alert_service_with_short_ttl.store_alert_session_mapping(alert_id, session_id)
        
        # Verify entries exist immediately
        assert alert_service_with_short_ttl.alert_exists(alert_id)
        assert alert_service_with_short_ttl.get_session_id_for_alert(alert_id) == session_id
        
        # Wait for TTL expiration (1.5 seconds to be safe)
        time.sleep(1.5)
        
        # Entries should be expired
        assert not alert_service_with_short_ttl.alert_exists(alert_id)
        assert alert_service_with_short_ttl.get_session_id_for_alert(alert_id) is None

    def test_cache_capacity_limits(self, mock_settings, mock_dependencies):
        """Test cache behavior when approaching maxsize limits."""
        with patch('tarsy.services.alert_service.TTLCache') as mock_ttl_cache:
            # Create caches with very small maxsize for testing
            mock_ttl_cache.side_effect = lambda maxsize, ttl: TTLCache(maxsize=3, ttl=3600)
            
            service = AlertService(mock_settings)
            
            # Fill caches beyond capacity
            alert_ids = [f"alert-{i}" for i in range(5)]
            session_ids = [f"session-{i}" for i in range(5)]
            
            for alert_id, session_id in zip(alert_ids, session_ids):
                service.register_alert_id(alert_id)
                service.store_alert_session_mapping(alert_id, session_id)
            
            # Due to maxsize=3, only the last 3 entries should exist
            # (cache eviction policy may vary, but total should not exceed maxsize)
            total_alerts = sum(1 for aid in alert_ids if service.alert_exists(aid))
            total_sessions = sum(1 for aid in alert_ids if service.get_session_id_for_alert(aid) is not None)
            
            assert total_alerts <= 3
            assert total_sessions <= 3

    def test_cache_performance_characteristics(self, mock_settings, mock_dependencies):
        """Test performance characteristics of cache operations."""
        service = AlertService(mock_settings)
        
        # Generate test data
        alert_ids = [str(uuid.uuid4()) for _ in range(100)]
        session_ids = [f"session-{i}" for i in range(100)]
        
        # Measure insertion time
        start_time = time.time()
        for alert_id, session_id in zip(alert_ids, session_ids):
            service.register_alert_id(alert_id)
            service.store_alert_session_mapping(alert_id, session_id)
        insertion_time = time.time() - start_time
        
        # Measure lookup time
        start_time = time.time()
        for alert_id in alert_ids:
            service.alert_exists(alert_id)
            service.get_session_id_for_alert(alert_id)
        lookup_time = time.time() - start_time
        
        # Operations should be fast (under reasonable thresholds)
        assert insertion_time < 1.0  # Should complete in under 1 second
        assert lookup_time < 0.5     # Lookups should be very fast
        
        # All entries should exist
        assert all(service.alert_exists(aid) for aid in alert_ids)

    def test_cache_memory_management(self, mock_settings, mock_dependencies):
        """Test that cache properly manages memory usage."""
        service = AlertService(mock_settings)
        
        # Add many entries
        alert_ids = [str(uuid.uuid4()) for _ in range(1000)]
        
        for alert_id in alert_ids:
            service.register_alert_id(alert_id)
            service.store_alert_session_mapping(alert_id, f"session-for-{alert_id}")
        
        # Check cache sizes are within expected bounds
        assert len(service.valid_alert_ids) <= 10000  # maxsize constraint
        assert len(service.alert_session_mapping) <= 10000  # maxsize constraint
        
        # Clear caches and verify memory is freed
        initial_alert_cache_size = len(service.valid_alert_ids)
        initial_session_cache_size = len(service.alert_session_mapping)
        
        service.clear_caches()
        
        assert len(service.valid_alert_ids) == 0
        assert len(service.alert_session_mapping) == 0
        
        # Verify we actually had entries before clearing
        assert initial_alert_cache_size > 0
        assert initial_session_cache_size > 0

    def test_cache_thread_safety_simulation(self, mock_settings, mock_dependencies):
        """Test cache behavior under concurrent-like access patterns."""
        service = AlertService(mock_settings)
        
        # Simulate concurrent operations by rapidly adding/checking entries
        alert_id_base = "concurrent-test"
        
        for i in range(100):
            alert_id = f"{alert_id_base}-{i}"
            session_id = f"session-{i}"
            
            # Rapid succession of operations
            service.register_alert_id(alert_id)
            assert service.alert_exists(alert_id)
            
            service.store_alert_session_mapping(alert_id, session_id)
            assert service.get_session_id_for_alert(alert_id) == session_id
        
        # Verify all entries are still accessible
        for i in range(100):
            alert_id = f"{alert_id_base}-{i}"
            assert service.alert_exists(alert_id)
            assert service.get_session_id_for_alert(alert_id) == f"session-{i}"

    def test_cache_behavior_after_service_close(self, mock_settings, mock_dependencies):
        """Test cache behavior after service cleanup."""
        service = AlertService(mock_settings)
        
        # Add test data
        alert_id = "close-test-alert"
        session_id = "close-test-session"
        
        service.register_alert_id(alert_id)
        service.store_alert_session_mapping(alert_id, session_id)
        
        # Verify data exists
        assert service.alert_exists(alert_id)
        assert service.get_session_id_for_alert(alert_id) == session_id
        
        # Close service (which should clear caches)
        import asyncio
        asyncio.run(service.close())
        
        # Caches should be cleared
        assert not service.alert_exists(alert_id)
        assert service.get_session_id_for_alert(alert_id) is None

    def test_mixed_cache_operations(self, mock_settings, mock_dependencies):
        """Test mixed operations on both caches."""
        service = AlertService(mock_settings)
        
        # Test scenario: some alerts have sessions, others don't
        alerts_with_sessions = [(f"with-session-{i}", f"session-{i}") for i in range(5)]
        alerts_without_sessions = [f"without-session-{i}" for i in range(5)]
        
        # Register alerts with sessions
        for alert_id, session_id in alerts_with_sessions:
            service.register_alert_id(alert_id)
            service.store_alert_session_mapping(alert_id, session_id)
        
        # Register alerts without sessions
        for alert_id in alerts_without_sessions:
            service.register_alert_id(alert_id)
        
        # Verify mixed state
        for alert_id, expected_session_id in alerts_with_sessions:
            assert service.alert_exists(alert_id)
            assert service.get_session_id_for_alert(alert_id) == expected_session_id
        
        for alert_id in alerts_without_sessions:
            assert service.alert_exists(alert_id)
            assert service.get_session_id_for_alert(alert_id) is None
        
        # Non-existent alerts should return appropriate responses
        assert not service.alert_exists("non-existent")
        assert service.get_session_id_for_alert("non-existent") is None
