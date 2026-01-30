"""
Unit tests for SlackService - Slack notification integration.

Tests Slack notification sending, message finding, formatting, and error handling.

Test Organization:
- TestSlackServiceInitialization: Service setup and configuration
- TestSendAlertNotification: Notification delivery workflows
- TestFindAlertMessage: Message discovery in Slack history
- TestReplyDirectly: Reply directly to Slack channel (non-threaded)
- TestPostThreadedReply: Post threaded reply functionality
- TestMessageFormatting: Slack message formatting
"""

from typing import Dict, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from slack_sdk.errors import SlackApiError

from tarsy.services.slack_service import SlackService
from tests.utils import MockFactory
from tarsy.models.processing_context import ChainContext
from tarsy.models.alert import ProcessingAlert


@pytest.fixture
def mock_settings_enabled():
    """Mock settings with Slack enabled using MockFactory."""
    return MockFactory.create_mock_settings(
        cors_origins=["http://localhost:5173"],
        slack_bot_token="xoxb-test-token",
        slack_channel="C12345678"
    )

@pytest.fixture
def mock_settings_disabled():
    """Mock settings with Slack disabled."""
    return MockFactory.create_mock_settings(
        slack_bot_token=None,
        slack_channel=None
    )

@pytest.fixture
def slack_service_enabled(mock_settings_enabled):
    """
    Create SlackService with Slack enabled and mocked dependencies.
    
    Returns configured service with mocked AsyncWebClient for testing.
    """
    with patch('tarsy.services.slack_service.AsyncWebClient'):
        service = SlackService(mock_settings_enabled)
        # Override client with a mock for testing
        service.client = AsyncMock()
        yield service


@pytest.fixture
def mock_slack_history() -> Dict:
    """Create mock Slack conversations_history response."""
    return {
        "messages": [
            {
                "ts": "1234567890.123456",
                "text": """Fingerprint: fingerprint-abc123
Cluster: main-cluster
Namespace: test-namespace
Message: Namespace is terminating""",
                "attachments": []
            },
            {
                "ts": "1234567891.123456",
                "text": "Other message",
                "attachments": []
            }
        ]
    }


@pytest.fixture
def mock_slack_history_with_attachments() -> Dict:
    """Create mock Slack response with attachments containing fingerprint."""
    return {
        "messages": [
            {
                "ts": "1234567890.123456",
                "text": "Alert notification",
                "attachments": [
                    {
                        "text": "Fingerprint: fingerprint-xyz789\nMessage: Test message",
                        "fallback": "Alert details"
                    }
                ]
            }
        ]
    }

@pytest.fixture
def create_chain_context():
    """Create mock ChainContext."""
    def _create(
        session_id: str = "test-session-123",
        slack_message_fingerprint: Optional[str] = None,
        **alert_overrides
    ) -> ChainContext:
        processing_alert = ProcessingAlert(
            alert_type="test-alert",
            timestamp=1234567890,
            slack_message_fingerprint=slack_message_fingerprint,
            alert_data={},
            **alert_overrides
        )
        return ChainContext(
            processing_alert=processing_alert,
            session_id=session_id,
            current_stage_name="test-stage"
        )
    return _create


@pytest.mark.unit
class TestSlackServiceInitialization:
    """
    Test SlackService initialization and configuration.
    
    Covers:
    - Enabled/disabled state based on configuration
    - WebClient instantiation when enabled
    - Proper handling of missing/invalid tokens
    - Channel configuration validation
    """
    
    def test_initialization_enabled(self, mock_settings_enabled) -> None:
        """Test initialization with Slack enabled creates client."""
        with patch('tarsy.services.slack_service.AsyncWebClient') as mock_webclient:
            service = SlackService(mock_settings_enabled)
            
            assert service.enabled is True
            assert service.client is not None
            assert service.settings == mock_settings_enabled
            mock_webclient.assert_called_once_with("xoxb-test-token")
    
    def test_initialization_disabled_no_token(self, mock_settings_disabled) -> None:
        """Test initialization with no Slack token disables service."""
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(mock_settings_disabled)
            
            assert service.enabled is False
            assert service.client is None
            assert service.settings == mock_settings_disabled
    
    def test_initialization_disabled_empty_token(self) -> None:
        """Test initialization with empty/whitespace token disables service."""
        settings = MockFactory.create_mock_settings(
            slack_bot_token="   ",
            slack_channel="C12345678"
        )
        
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(settings)

            assert service.enabled is False
    
    def test_initialization_disabled_no_channel(self) -> None:
        """Test initialization with no Slack channel disables service."""
        settings = MockFactory.create_mock_settings(
            slack_bot_token="xoxb-test-token",
            slack_channel=None
        )
        
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(settings)

            assert service.enabled is False
    
    def test_initialization_disabled_empty_channel(self) -> None:
        """Test initialization with empty channel disables service."""
        settings = MockFactory.create_mock_settings(
            slack_bot_token="xoxb-test-token",
            slack_channel="   "
        )
        
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(settings)
            
            assert service.enabled is False


@pytest.mark.unit
class TestSendAlertNotification:
    """
    Test sending Slack notifications for alert processing events.
    
    Covers:
    - Successful notification delivery with analysis results
    - Error notification delivery for failed processing
    - Disabled service behavior (early return)
    - Fingerprint validation (None, empty, whitespace)
    - Message discovery failures
    - Reply thread failures
    - Exception handling
    
    Integration with:
    - find_alert_message(): Locates original alert in history
    - reply_to_alert_directly(): Posts threaded reply
    """
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_success_with_threading(self, slack_service_enabled, create_chain_context) -> None:
        """Test successful alert notification with analysis."""
        # Setup mocks
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=True)
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=False)
        
        chain_context = create_chain_context(slack_message_fingerprint="alert-fingerprint-456")
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="Alert analysis completed successfully")
        

        assert result is True
        slack_service_enabled.post_threaded_reply.assert_called_once_with(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis="Alert analysis completed successfully",
            error_msg=None,
            is_pause=False,
        )
        slack_service_enabled.reply_to_chat_directly.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_with_error_with_threading(self, slack_service_enabled, create_chain_context) -> None:
        """Test sending alert notification with error instead of analysis."""
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=True)
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=False)

        chain_context = create_chain_context(slack_message_fingerprint="alert-fingerprint-456")
        result = await slack_service_enabled.send_alert_error_notification(chain_context, error_msg="Processing failed: timeout")
        
        assert result is True
        slack_service_enabled.post_threaded_reply.assert_called_once_with(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis=None,
            error_msg="Processing failed: timeout",
            is_pause=False,
        )
        slack_service_enabled.reply_to_chat_directly.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_notification_with_pause_with_threading(self, slack_service_enabled, create_chain_context) -> None:
        """Test sending alert notification for paused session."""
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=True)
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=False)

        chain_context = create_chain_context(slack_message_fingerprint="alert-fingerprint-456")
        result = await slack_service_enabled.send_alert_paused_notification(chain_context, pause_message="Session paused after 10 iterations")
        
        assert result is True
        slack_service_enabled.post_threaded_reply.assert_called_once_with(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis="Session paused after 10 iterations",
            error_msg=None,
            is_pause=True,
        )
        slack_service_enabled.reply_to_chat_directly.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_notification_success_without_threading(self, slack_service_enabled, create_chain_context) -> None:
        """Test successful alert notification without threading."""
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=True)
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=False)
        
        chain_context = create_chain_context(slack_message_fingerprint=None)
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="Alert analysis completed successfully")
        
        assert result is True
        slack_service_enabled.reply_to_chat_directly.assert_called_once_with(
            session_id=chain_context.session_id,
            analysis="Alert analysis completed successfully",
            error_msg=None,
            is_pause=False,
        )

        slack_service_enabled.post_threaded_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_notification_with_pause_without_threading(self, slack_service_enabled, create_chain_context) -> None:
        """Test paused alert notification without threading."""
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=True)
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=False)
        
        chain_context = create_chain_context(slack_message_fingerprint=None)
        result = await slack_service_enabled.send_alert_paused_notification(chain_context, pause_message="Session paused - resume to continue")
        
        assert result is True
        slack_service_enabled.reply_to_chat_directly.assert_called_once_with(
            session_id=chain_context.session_id,
            analysis="Session paused - resume to continue",
            error_msg=None,
            is_pause=True,
        )

        slack_service_enabled.post_threaded_reply.assert_not_called() 
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_disabled(self, mock_settings_disabled, create_chain_context) -> None:
        """Test notification returns False when Slack is disabled."""
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(mock_settings_disabled)
            
            chain_context = create_chain_context(slack_message_fingerprint="test-fingerprint")
            result = await service.send_alert_analysis_notification(chain_context, analysis="test analysis")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_no_fingerprint(self, slack_service_enabled, create_chain_context) -> None:
        """Test notification sends direct message when no fingerprint provided."""
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=True)
        
        chain_context = create_chain_context(slack_message_fingerprint=None)
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="test analysis")
        
        assert result is True
        slack_service_enabled.reply_to_chat_directly.assert_called_once_with(
            session_id=chain_context.session_id,
            analysis="test analysis",
            error_msg=None,
            is_pause=False,
        )
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_empty_fingerprint(self, slack_service_enabled, create_chain_context) -> None:
        """Test notification sends direct message when empty fingerprint provided."""
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=True)
        
        chain_context = create_chain_context(slack_message_fingerprint="")
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="test analysis")
        
        assert result is True
        slack_service_enabled.reply_to_chat_directly.assert_called_once_with(
            session_id=chain_context.session_id,
            analysis="test analysis",
            error_msg=None,
            is_pause=False,
        )

    @pytest.mark.asyncio
    async def test_send_alert_notification_whitespace_fingerprint(self, slack_service_enabled, create_chain_context) -> None:
        """Test notification sends direct message when whitespace-only fingerprint provided."""
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=True)
        
        chain_context = create_chain_context(slack_message_fingerprint="   ")
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="test analysis")
        
        assert result is True
        slack_service_enabled.reply_to_chat_directly.assert_called_once_with(
            session_id=chain_context.session_id,
            analysis="test analysis",
            error_msg=None,
            is_pause=False,
        )

    
    @pytest.mark.asyncio
    async def test_send_alert_notification_message_not_found(self, slack_service_enabled, create_chain_context) -> None:
        """Test notification fails when original message not found in Slack."""
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=False)
        
        chain_context = create_chain_context(slack_message_fingerprint="unknown-fingerprint")
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="test analysis")
        
        assert result is False
        slack_service_enabled.post_threaded_reply.assert_called_once_with(
            session_id=chain_context.session_id,
            slack_message_fingerprint="unknown-fingerprint",
            analysis="test analysis",
            error_msg=None,
            is_pause=False,
        )
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_reply_fails(self, slack_service_enabled, create_chain_context) -> None:
        """Test notification handles reply failure gracefully."""
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=False)
        
        chain_context = create_chain_context(slack_message_fingerprint="alert-fingerprint")
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="test analysis")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_alert_notification_exception_handling(self, slack_service_enabled, create_chain_context) -> None:
        """Test notification handles exceptions gracefully and returns False."""
        slack_service_enabled.post_threaded_reply = AsyncMock(
            side_effect=Exception("Connection timeout")
        )
        
        chain_context = create_chain_context(slack_message_fingerprint="alert-fingerprint")
        result = await slack_service_enabled.send_alert_analysis_notification(chain_context, analysis="test analysis")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_paused_notification_disabled(self, mock_settings_disabled, create_chain_context) -> None:
        """Test paused notification returns False when Slack is disabled."""
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(mock_settings_disabled)
            
            chain_context = create_chain_context(slack_message_fingerprint="test-fingerprint")
            result = await service.send_alert_paused_notification(chain_context, pause_message="test pause")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_started_notification_with_fingerprint(self, slack_service_enabled, create_chain_context) -> None:
        """Test sending started notification with fingerprint (Slack-originated alert)."""
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=True)
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=False)
        
        chain_context = create_chain_context(slack_message_fingerprint="alert-fingerprint-789")
        result = await slack_service_enabled.send_alert_started_notification(chain_context)
        
        assert result is True
        slack_service_enabled.post_threaded_reply.assert_called_once()
        # Verify the start message contains expected text
        call_args = slack_service_enabled.post_threaded_reply.call_args
        assert call_args[1]['session_id'] == chain_context.session_id
        assert call_args[1]['slack_message_fingerprint'] == "alert-fingerprint-789"
        assert "Processing alert started" in call_args[1]['analysis']
        assert call_args[1]['error_msg'] is None
        
        slack_service_enabled.reply_to_chat_directly.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_started_notification_without_fingerprint(self, slack_service_enabled, create_chain_context) -> None:
        """Test started notification is skipped when no fingerprint (non-Slack alert)."""
        slack_service_enabled.post_threaded_reply = AsyncMock(return_value=True)
        slack_service_enabled.reply_to_chat_directly = AsyncMock(return_value=True)
        
        chain_context = create_chain_context(slack_message_fingerprint=None)
        result = await slack_service_enabled.send_alert_started_notification(chain_context)
        
        # Should return False and skip notification
        assert result is False
        slack_service_enabled.post_threaded_reply.assert_not_called()
        slack_service_enabled.reply_to_chat_directly.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_started_notification_disabled(self, mock_settings_disabled, create_chain_context) -> None:
        """Test started notification returns False when Slack is disabled."""
        with patch('tarsy.services.slack_service.AsyncWebClient'):
            service = SlackService(mock_settings_disabled)
            
            chain_context = create_chain_context(slack_message_fingerprint="test-fingerprint")
            result = await service.send_alert_started_notification(chain_context)
            
            assert result is False


@pytest.mark.unit
class TestFindAlertMessage:
    """
    Test finding alert message to reply to in Slack channel history.
    
    Covers:
    - Fingerprint matching in message text
    - Fingerprint matching in attachment text
    - Empty message history
    - Message not found scenarios
    - Slack API errors (channel_not_found, etc.)
    
    Search Strategy:
    - Searches last 24 hours of channel history
    - Combines message text with all attachment text
    - Returns first matching message timestamp
    """
    
    @pytest.mark.asyncio
    async def test_find_alert_message_in_text(self, slack_service_enabled, mock_slack_history) -> None:
        """Test finding alert message by fingerprint in message text."""
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_slack_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("fingerprint-abc123")
        
        assert result == "1234567890.123456"
    
    @pytest.mark.asyncio
    async def test_find_alert_message_in_attachments(
        self, 
        slack_service_enabled,
        mock_slack_history_with_attachments
    ) -> None:
        """Test finding alert message by fingerprint in message attachments."""
        slack_service_enabled.client.conversations_history = AsyncMock(
            return_value=mock_slack_history_with_attachments
        )
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("fingerprint-xyz789")
        
        assert result == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_find_alert_message_no_attachments_key(self, slack_service_enabled) -> None:
        """Test handling messages without 'attachments' key."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Fingerprint: fingerprint-simple-789\nMessage: Test message"
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("fingerprint-simple-789")
        
        assert result == "1234567890.123456"
    
    @pytest.mark.asyncio
    async def test_find_alert_message_not_found(self, slack_service_enabled) -> None:
        """Test when alert message with fingerprint is not found."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Unrelated message",
                    "attachments": []
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("nonexistent-fingerprint")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_find_alert_message_empty_history(self, slack_service_enabled) -> None:
        """Test handling of empty message history."""
        mock_history = {"messages": []}
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("test-fingerprint")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_find_alert_message_api_error(self, slack_service_enabled) -> None:
        """Test handling Slack API error during message search."""
        # Create a proper response object that supports subscript access
        mock_response = Mock()
        mock_response.__getitem__ = Mock(return_value="channel_not_found")
        
        slack_service_enabled.client.conversations_history = AsyncMock(
            side_effect=SlackApiError("Error", mock_response)
        )
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("test-fingerprint")
        
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message_fingerprint,search_fingerprint,should_match",
        [
            ("Fingerprint: ABC123", "Fingerprint: ABC123", True),
            ("Fingerprint: ABC123", "fingerprint: abc123", True),
            ("fingerprint: abc123", "FINGERPRINT: ABC123", True),
            ("FINGERPRINT: ABC123", "fingerprint: abc123", True),
            ("FiNgErPrInT: AbC123", "fingerprint: abc123", True),
            ("Fingerprint: ABC123", "Fingerprint: XYZ789", False),
        ],
    )
    async def test_find_alert_message_case_insensitive(
        self, 
        slack_service_enabled, 
        message_fingerprint: str,
        search_fingerprint: str,
        should_match: bool
    ) -> None:
        """Test fingerprint matching is case-insensitive."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": f"{message_fingerprint}\nAlert: Test alert",
                    "attachments": []
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message(search_fingerprint)
        
        if should_match:
            assert result == "1234567890.123456"
        else:
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message_fingerprint,search_fingerprint",
        [
            ("Fingerprint: ABC123\n", "Fingerprint: ABC123"),
            ("Fingerprint: ABC123", "Fingerprint: ABC123\n"),
            ("Fingerprint:    ABC123", "Fingerprint: ABC123"),
            ("Fingerprint:\tABC123", "Fingerprint: ABC123"),
            ("Fingerprint:  \n  ABC123", "Fingerprint: ABC123"),
            ("  Fingerprint:  ABC123  ", "Fingerprint: ABC123"),
            ("Fingerprint:\nABC123", "Fingerprint: ABC123"),
        ],
    )
    async def test_find_alert_message_whitespace_normalization(
        self, 
        slack_service_enabled, 
        message_fingerprint: str,
        search_fingerprint: str
    ) -> None:
        """Test fingerprint matching normalizes whitespace (spaces, tabs, newlines)."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": f"Alert: Test alert\n{message_fingerprint}\nEnvironment: prod",
                    "attachments": []
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message(search_fingerprint)
        
        assert result == "1234567890.123456"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message_text,search_fingerprint",
        [
            ("Fingerprint: XYZ789\nAlert message", "fingerprint: xyz789"),
            ("Alert: High CPU\nFINGERPRINT: XYZ789", "xyz789"),
            ("Alert message\nEnvironment: prod\nFingerprint: XYZ789", "FINGERPRINT:   XYZ789"),
            ("Fingerprint:XYZ789", "fingerprint:xyz789"),
            ("FINGERPRINT:\n\nXYZ789", "fingerprint: xyz789"),
        ],
    )
    async def test_find_alert_message_case_and_whitespace_combined(
        self, 
        slack_service_enabled, 
        message_text: str,
        search_fingerprint: str
    ) -> None:
        """Test fingerprint matching with both case-insensitivity and whitespace normalization."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": message_text,
                    "attachments": []
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message(search_fingerprint)
        
        assert result == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_find_alert_message_in_attachment_case_insensitive(self, slack_service_enabled) -> None:
        """Test case-insensitive matching in message attachments."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Alert notification",
                    "attachments": [
                        {
                            "text": "FINGERPRINT: ALERT-999\nMessage: Critical issue",
                            "fallback": "Alert details"
                        }
                    ]
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("fingerprint: alert-999")
        
        assert result == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_find_alert_message_in_fallback_normalized(self, slack_service_enabled) -> None:
        """Test whitespace normalization in attachment fallback field."""
        mock_history = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Alert",
                    "attachments": [
                        {
                            "text": "",
                            "fallback": "Fingerprint:  \n  ALERT-888  \nCritical"
                        }
                    ]
                }
            ]
        }
        slack_service_enabled.client.conversations_history = AsyncMock(return_value=mock_history)
        
        with patch('time.time', return_value=1000000000.0):
            result = await slack_service_enabled.find_alert_message("fingerprint: alert-888")
        
        assert result == "1234567890.123456"


@pytest.mark.unit
class TestReplyDirectly:
    """
    Test replying directly to Slack channel (non-threaded).
    
    Covers:
    - Successful direct reply with analysis
    - Direct reply with error messages
    - Slack API errors during posting
    
    Behavior:
    - Formats message via _format_alert_message()
    - Posts to configured channel without threading
    """
    
    @pytest.mark.asyncio
    async def test_reply_directly_success(self, slack_service_enabled) -> None:
        """Test successful direct reply to channel."""
        slack_service_enabled.client.chat_postMessage = AsyncMock()
        
        result = await slack_service_enabled.reply_to_chat_directly(
            session_id="test-session-123",
            analysis="Analysis completed",
            error_msg=None
        )
        
        assert result is True
        slack_service_enabled.client.chat_postMessage.assert_called_once()
        
        # Verify call structure
        call_kwargs = slack_service_enabled.client.chat_postMessage.call_args.kwargs
        assert call_kwargs['channel'] == "C12345678"
        assert 'thread_ts' not in call_kwargs  # Direct message, no threading
        assert 'attachments' in call_kwargs
    
    @pytest.mark.asyncio
    async def test_reply_directly_with_error(self, slack_service_enabled) -> None:
        """Test replying with error message instead of analysis."""
        slack_service_enabled.client.chat_postMessage = AsyncMock()
        
        result = await slack_service_enabled.reply_to_chat_directly(
            session_id="test-session-123",
            analysis=None,
            error_msg="Processing failed"
        )
        
        assert result is True
        
        # Verify error is included in message
        call_kwargs = slack_service_enabled.client.chat_postMessage.call_args.kwargs
        attachments = call_kwargs['attachments']
        assert any("Error" in str(att) for att in attachments)
    
    @pytest.mark.asyncio
    async def test_reply_directly_api_error(self, slack_service_enabled) -> None:
        """Test handling Slack API error during reply."""
        mock_response = Mock()
        mock_response.__getitem__ = Mock(return_value="channel_not_found")
        
        slack_service_enabled.client.chat_postMessage = AsyncMock(
            side_effect=SlackApiError("Error", mock_response)
        )
        
        result = await slack_service_enabled.reply_to_chat_directly(
            session_id="test-session",
            analysis="test"
        )
        
        assert result is False


@pytest.mark.unit
class TestPostThreadedReply:
    """
    Test posting threaded replies to alert messages.
    
    Covers:
    - Successful threaded reply with analysis
    - Threaded reply with error messages
    - Message not found scenario
    - Slack API errors during posting
    
    Threading Behavior:
    - Finds original message via find_alert_message()
    - Formats message via _format_alert_message()
    - Posts to configured channel as threaded reply
    """
    
    @pytest.mark.asyncio
    async def test_post_threaded_reply_success(self, slack_service_enabled) -> None:
        """Test successful threaded reply to alert message."""
        slack_service_enabled.find_alert_message = AsyncMock(return_value="1234567890.123456")
        slack_service_enabled.client.chat_postMessage = AsyncMock()
        
        result = await slack_service_enabled.post_threaded_reply(
            session_id="test-session-123",
            slack_message_fingerprint="fingerprint-abc123",
            analysis="Analysis completed",
            error_msg=None
        )
        
        assert result is True
        slack_service_enabled.find_alert_message.assert_called_once_with(
            slack_message_fingerprint="fingerprint-abc123"
        )
        slack_service_enabled.client.chat_postMessage.assert_called_once()
        
        # Verify call structure includes thread_ts
        call_kwargs = slack_service_enabled.client.chat_postMessage.call_args.kwargs
        assert call_kwargs['channel'] == "C12345678"
        assert call_kwargs['thread_ts'] == "1234567890.123456"
        assert 'attachments' in call_kwargs
    
    @pytest.mark.asyncio
    async def test_post_threaded_reply_with_error(self, slack_service_enabled) -> None:
        """Test threaded reply with error message instead of analysis."""
        slack_service_enabled.find_alert_message = AsyncMock(return_value="1234567890.123456")
        slack_service_enabled.client.chat_postMessage = AsyncMock()
        
        result = await slack_service_enabled.post_threaded_reply(
            session_id="test-session-123",
            slack_message_fingerprint="fingerprint-abc123",
            analysis=None,
            error_msg="Processing failed"
        )
        
        assert result is True
        
        # Verify error is included in message
        call_kwargs = slack_service_enabled.client.chat_postMessage.call_args.kwargs
        attachments = call_kwargs['attachments']
        assert any("Error" in str(att) for att in attachments)
    
    @pytest.mark.asyncio
    async def test_post_threaded_reply_message_not_found(self, slack_service_enabled) -> None:
        """Test threaded reply fails when original message not found."""
        slack_service_enabled.find_alert_message = AsyncMock(return_value=None)
        
        result = await slack_service_enabled.post_threaded_reply(
            session_id="test-session-123",
            slack_message_fingerprint="nonexistent-fingerprint",
            analysis="test analysis"
        )
        
        assert result is False
        slack_service_enabled.find_alert_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_post_threaded_reply_api_error(self, slack_service_enabled) -> None:
        """Test handling Slack API error during threaded reply."""
        slack_service_enabled.find_alert_message = AsyncMock(return_value="1234567890.123456")
        
        mock_response = Mock()
        mock_response.__getitem__ = Mock(return_value="message_not_found")
        
        slack_service_enabled.client.chat_postMessage = AsyncMock(
            side_effect=SlackApiError("Error", mock_response)
        )
        
        result = await slack_service_enabled.post_threaded_reply(
            session_id="test-session",
            slack_message_fingerprint="test-fingerprint",
            analysis="test"
        )
        
        assert result is False


@pytest.mark.unit
class TestMessageFormatting:
    """
    Test Slack message formatting for various scenarios.
    
    Covers:
    - Analysis message formatting
    - Error message formatting
    - Session link inclusion
    
    Message Structure:
    - Uses Slack attachments API
    - Colors: "good" for analysis messages, "danger" for error messages, "warning" for pause messages
    - Text: Formatted with markdown
    - Includes dashboard link for detailed analysis
    """
    
    def test_format_alert_message_with_analysis(self, slack_service_enabled) -> None:
        """Test formatting message with successful analysis."""
        result = slack_service_enabled._format_alert_message(
            session_id="test-session-123",
            analysis="Alert resolved: Pod restarted successfully"
        )
        
        # Verify structure
        assert result['channel'] == "C12345678"
        assert len(result['attachments']) == 1
        
        # Verify content
        attachment = result['attachments'][0]
        assert attachment['color'] == "good"
        assert "*Analysis:*" in attachment['text']
        assert "Alert resolved: Pod restarted successfully" in attachment['text']
        assert "*View Analysis Details:* http://localhost:5173/sessions/test-session-123" in attachment['text']
        
    def test_format_alert_message_with_error(self, slack_service_enabled) -> None:
        """Test formatting message with processing error."""
        result = slack_service_enabled._format_alert_message(
            session_id="test-session-456",
            error_msg="Connection timeout to Kubernetes API"
        )
        
        attachment = result['attachments'][0]
        assert attachment['color'] == "danger"
        assert "*Error:*" in attachment['text']
        assert "Connection timeout to Kubernetes API" in attachment['text']
        assert "*View Analysis Details:* http://localhost:5173/sessions/test-session-456" in attachment['text']

    def test_format_alert_message_with_pause(self, slack_service_enabled) -> None:
        """Test formatting message with pause status."""
        result = slack_service_enabled._format_alert_message(
            session_id="test-session-789",
            analysis="Session paused after 10 iterations - resume to continue",
            is_pause=True
        )
        
        attachment = result['attachments'][0]
        assert attachment['color'] == "warning"
        assert "*Analysis:*" in attachment['text']
        assert "Session paused after 10 iterations - resume to continue" in attachment['text']
        assert "*View Analysis Details:* http://localhost:5173/sessions/test-session-789" in attachment['text']
