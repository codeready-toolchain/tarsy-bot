"""
Integration tests for integration between AlertService and SlackService.
"""

import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import alert_to_api_format


@pytest.mark.integration
class TestSlackNotificationIntegration:
    """
    Test integration between AlertService and SlackService.
    
    Verifies that:
    - Started processing triggers Slack notification with start message (if fingerprint exists)
    - Successful processing triggers Slack notification with summary
    - Failed processing triggers Slack notification with error
    - Paused processing triggers Slack notification with pause message
    """
    
    @pytest.mark.asyncio
    async def test_successful_processing_sends_slack_notification(
        self,
        alert_service_with_slack,
        sample_alert_with_fingerprint,
    ) -> None:
        """Test that successful alert processing sends Slack notification with summary."""
        alert_service = alert_service_with_slack
        
        # Process alert
        chain_context = alert_to_api_format(sample_alert_with_fingerprint)
        result = await alert_service.process_alert(chain_context)
        
        # Verify processing completed
        assert result is not None
        assert "# Alert Analysis Report" in result
        
        # Verify Slack start notification was sent (fingerprint exists)
        alert_service.slack_service.send_alert_started_notification.assert_called_once()
        start_call_args = alert_service.slack_service.send_alert_started_notification.call_args
        start_chain_context = start_call_args.args[0]
        assert start_chain_context.session_id == chain_context.session_id
        assert start_chain_context.processing_alert.slack_message_fingerprint == "test-fingerprint-abc123"
        
        # Verify Slack completion notification was sent
        alert_service.slack_service.send_alert_analysis_notification.assert_called_once()
        
        call_args = alert_service.slack_service.send_alert_analysis_notification.call_args
        passed_chain_context = call_args.args[0]
        call_kwargs = call_args.kwargs
        
        assert passed_chain_context.session_id == chain_context.session_id
        assert passed_chain_context.processing_alert.slack_message_fingerprint == "test-fingerprint-abc123"
        assert 'analysis' in call_kwargs

    @pytest.mark.asyncio
    async def test_failed_processing_sends_error_notification(
        self,
        alert_service_with_slack,
        sample_alert_with_fingerprint,
    ) -> None:
        """Test that failed processing sends Slack notification with error."""
        alert_service = alert_service_with_slack
        
        chain_context = alert_to_api_format(sample_alert_with_fingerprint)
        
        # Get the original callable methods (not side_effect which may be None)
        original_create = alert_service.agent_factory.create_agent
        original_get_with_config = alert_service.agent_factory.get_agent_with_config
        
        def create_failing_agent(agent_identifier, mcp_client):
            # Call the original mocked method to get an agent
            agent = original_create(agent_identifier, mcp_client)
            # Override process_alert to raise an exception
            agent.process_alert = AsyncMock(side_effect=Exception("Agent processing failed"))
            return agent
        
        def get_failing_agent_with_config(agent_identifier, mcp_client, execution_config):
            # Call the original mocked method to get an agent
            agent = original_get_with_config(agent_identifier, mcp_client, execution_config)
            # Override process_alert to raise an exception
            agent.process_alert = AsyncMock(side_effect=Exception("Agent processing failed"))
            return agent
        
        # Use patch.object with wraps to intercept and modify the agent
        with patch.object(
            alert_service.agent_factory,
            'create_agent',
            side_effect=create_failing_agent
        ), patch.object(
            alert_service.agent_factory,
            'get_agent_with_config',
            side_effect=get_failing_agent_with_config
        ):
            result = await alert_service.process_alert(chain_context)
            
            # Verify error response
            assert "# Alert Processing Error" in result
            
            # Verify Slack start notification was sent (fingerprint exists)
            alert_service.slack_service.send_alert_started_notification.assert_called_once()
            start_call_args = alert_service.slack_service.send_alert_started_notification.call_args
            start_chain_context = start_call_args.args[0]
            assert start_chain_context.session_id == chain_context.session_id
            assert start_chain_context.processing_alert.slack_message_fingerprint == "test-fingerprint-abc123"
            
            # Verify Slack error notification was sent
            alert_service.slack_service.send_alert_error_notification.assert_called_once()
            
            call_args = alert_service.slack_service.send_alert_error_notification.call_args
            passed_chain_context = call_args.args[0]
            call_kwargs = call_args.kwargs
            
            assert passed_chain_context.session_id == chain_context.session_id
            assert passed_chain_context.processing_alert.slack_message_fingerprint == "test-fingerprint-abc123"
            assert 'error_msg' in call_kwargs
            assert call_kwargs['error_msg'] is not None
