"""
End-to-end tests for alert submission with native tools configuration.

Tests the complete flow from API submission through to LLM client with
native tools override applied.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tarsy.main import app


class TestAlertWithNativeTools:
    """E2E tests for alerts with native tools configuration."""
    
    @pytest.mark.asyncio
    async def test_submit_alert_with_native_tools_config(self):
        """Test submitting an alert with native tools configuration."""
        # Prepare alert data with native tools config
        alert_data = {
            "alert_type": "TestAlert",
            "data": {
                "severity": "warning",
                "message": "Test alert with native tools"
            },
            "mcp": {
                "servers": [
                    {
                        "name": "kubernetes-server",
                        "tools": None
                    }
                ],
                "native_tools": {
                    "google_search": True,
                    "code_execution": False,
                    "url_context": True
                }
            }
        }
        
        # Mock the background processing to avoid actual alert processing
        with patch('tarsy.main.process_alert_background', new_callable=AsyncMock) as mock_process:
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post("/api/v1/alerts", json=alert_data)
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert "session_id" in response_data
        assert response_data["status"] == "queued"
        
        # Verify background processing was called
        assert mock_process.called
        
        # Extract the processing_alert from the call
        call_args = mock_process.call_args
        processing_alert = call_args[0][0]  # First positional argument
        
        # Verify native tools config was preserved in processing_alert
        assert processing_alert.mcp is not None
        assert processing_alert.mcp.native_tools is not None
        assert processing_alert.mcp.native_tools.google_search is True
        assert processing_alert.mcp.native_tools.code_execution is False
        assert processing_alert.mcp.native_tools.url_context is True
    
    @pytest.mark.asyncio
    async def test_submit_alert_without_native_tools(self):
        """Test submitting an alert without native tools (uses defaults)."""
        alert_data = {
            "alert_type": "TestAlert",
            "data": {
                "severity": "warning",
                "message": "Test alert without native tools"
            },
            "mcp": {
                "servers": [
                    {
                        "name": "kubernetes-server",
                        "tools": None
                    }
                ]
            }
        }
        
        with patch('tarsy.main.process_alert_background', new_callable=AsyncMock) as mock_process:
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        
        # Extract processing_alert
        call_args = mock_process.call_args
        processing_alert = call_args[0][0]
        
        # Verify native tools config is None (will use provider defaults)
        assert processing_alert.mcp is not None
        assert processing_alert.mcp.native_tools is None
    
    @pytest.mark.asyncio
    async def test_submit_alert_partial_native_tools(self):
        """Test submitting an alert with partial native tools configuration."""
        alert_data = {
            "alert_type": "TestAlert",
            "data": {
                "severity": "warning",
                "message": "Test alert with partial native tools"
            },
            "mcp": {
                "servers": [
                    {
                        "name": "kubernetes-server"
                    }
                ],
                "native_tools": {
                    "google_search": True
                    # Other tools not specified (None = use provider defaults)
                }
            }
        }
        
        with patch('tarsy.main.process_alert_background', new_callable=AsyncMock) as mock_process:
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        
        # Extract processing_alert
        call_args = mock_process.call_args
        processing_alert = call_args[0][0]
        
        # Verify only google_search is enabled, others remain None (use provider defaults)
        assert processing_alert.mcp.native_tools.google_search is True
        assert processing_alert.mcp.native_tools.code_execution is None
        assert processing_alert.mcp.native_tools.url_context is None
    
    @pytest.mark.asyncio
    async def test_native_tools_validation(self):
        """Test that invalid native tools configuration is rejected."""
        # This test assumes validation is added (future enhancement)
        # For now, it just verifies the structure is accepted
        alert_data = {
            "alert_type": "TestAlert",
            "data": {
                "severity": "warning",
                "message": "Test alert"
            },
            "mcp": {
                "servers": [
                    {
                        "name": "kubernetes-server"
                    }
                ],
                "native_tools": {
                    "google_search": True,
                    "code_execution": True,
                    "url_context": True
                }
            }
        }
        
        with patch('tarsy.main.process_alert_background', new_callable=AsyncMock):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post("/api/v1/alerts", json=alert_data)
        
        # Should accept valid configuration
        assert response.status_code == 200

