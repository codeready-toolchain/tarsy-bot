"""
Slack Notification Service
Handles sending notifications to Slack channel for alert processing events.
"""

import time
from typing import Any, Dict, Optional

from tarsy.models.processing_context import ChainContext
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from tarsy.config.settings import Settings
from tarsy.utils.logger import get_module_logger


logger = get_module_logger(__name__)


class SlackService:
    """
    Service for sending notifications to Slack channels.
    
    Supports:
    - Alert processing started notifications (only for Slack-originated alerts)
    - Alert processing completion notifications
    - Alert processing failure notifications
    - Alert processing paused notifications
    - System error notifications
    """

    def __init__(self, settings: Settings):
        """
        Initialize Slack service with settings.
        
        Args:
            settings: Application settings containing Slack configuration
        """
        self.settings = settings

        # Check if Slack is configured
        has_slack_token = bool(self.settings.slack_bot_token and self.settings.slack_bot_token.strip())
        has_slack_channel = bool(self.settings.slack_channel and self.settings.slack_channel.strip())
        
        self.enabled = has_slack_token and has_slack_channel

        if self.enabled:
            self.client = AsyncWebClient(self.settings.slack_bot_token)
            logger.info(f"Slack notifications enabled for channel {self.settings.slack_channel}")
        else:
            self.client = None
            if has_slack_token and not has_slack_channel:
                logger.warning("Slack bot token configured but channel is missing - Slack notifications disabled")
            elif has_slack_channel and not has_slack_token:
                logger.warning("Slack channel configured but bot token is missing - Slack notifications disabled")
            else:
                logger.info("Slack notifications disabled - missing Slack bot token and channel configuration")

    async def send_alert_analysis_notification(
        self,
        chain_context: ChainContext,
        analysis: str,
    ) -> bool:
        """
        Send notification for successful alert processing.
        
        Args:
            chain_context: Chain context containing session ID and processing alert
            analysis: Analysis result from successful processing
                    
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        return await self._send_alert_notification(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis=analysis,
            error_msg=None,
        )

    async def send_alert_error_notification(
        self,
        chain_context: ChainContext,
        error_msg: str,
    ) -> bool:
        """
        Send notification for failed alert processing.
        
        Args:
            chain_context: Chain context containing session ID and processing alert
            error_msg: Error message describing the failure
                    
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        return await self._send_alert_notification(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis=None,
            error_msg=error_msg,
        )

    async def send_alert_paused_notification(
        self,
        chain_context: ChainContext,
        pause_message: str,
    ) -> bool:
        """
        Send notification for paused alert processing.
        
        Args:
            chain_context: Chain context containing session ID and processing alert
            pause_message: Message describing the pause state
                    
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        return await self._send_alert_notification(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis=pause_message,
            error_msg=None,
            is_pause=True,
        )

    async def send_alert_started_notification(
        self,
        chain_context: ChainContext,
    ) -> bool:
        """
        Send notification for started alert processing.
        
        Only sends if a slack_message_fingerprint is present (meaning the alert
        originated from Slack). This provides immediate feedback in the Slack thread.
        
        Args:
            chain_context: Chain context containing session ID and processing alert
                    
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        # Only send start notification if fingerprint exists
        if not chain_context.processing_alert.slack_message_fingerprint:
            logger.debug("No Slack fingerprint - skipping start notification")
            return False
            
        start_message = "🔄 Processing alert started. This may take a few minutes..."
        return await self._send_alert_notification(
            session_id=chain_context.session_id,
            slack_message_fingerprint=chain_context.processing_alert.slack_message_fingerprint,
            analysis=start_message,
            error_msg=None,
        )

    async def _send_alert_notification(
        self,
        session_id: str,
        slack_message_fingerprint: Optional[str] = None,
        analysis: Optional[str] = None,
        error_msg: Optional[str] = None,
        is_pause: bool = False,
    ) -> bool:
        """
        Send notification for alert processing event.
        
        Args:
            session_id: Session ID for tracking
            slack_message_fingerprint: Slack message fingerprint for Slack notification threading
            analysis: Analysis result (for successful processing)
            error_msg: Error message (for failed processing)
            is_pause: Whether this is a pause notification (for color coding)
                    
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Slack notifications disabled - skipping")
            return False

        try:
            if slack_message_fingerprint and slack_message_fingerprint.strip():
                logger.info(f"Slack notification threading is provided for session {session_id}, sending threaded notification")
                return await self.post_threaded_reply(
                    session_id=session_id,
                    slack_message_fingerprint=slack_message_fingerprint,
                    analysis=analysis,
                    error_msg=error_msg,
                    is_pause=is_pause,
                )

            logger.info(f"Slack notification threading is not provided for session {session_id}, sending standard notification")
            return await self.reply_to_chat_directly(
                session_id=session_id,
                analysis=analysis,
                error_msg=error_msg,
                is_pause=is_pause,
            )

        except Exception as e:
            logger.error(f"Error sending Slack notification for session {session_id}: {str(e)}")
            return False

    async def find_alert_message(
        self, 
        slack_message_fingerprint: str,
    ) -> Optional[str]:
        """ 
        Find the target message to reply to in the Slack channel history.
        
        Args:
            slack_message_fingerprint: Slack message fingerprint for Slack message threading
        
        Returns:
            Message timestamp (ts) if found, None otherwise
        """
            
        try:
            # last 24 hours
            current_time = time.time()
            lookback_seconds = 24 * 3600
            oldest = current_time - lookback_seconds

            logger.debug(f"Searching for fingerprint: '{slack_message_fingerprint}' (length: {len(slack_message_fingerprint)})")

            # Search for messages in the channel
            history = await self.client.conversations_history(
                channel=self.settings.slack_channel,
                oldest=str(int(oldest)),
                limit=50
            )
            
            logger.debug(f"Found {len(history['messages'])} messages in channel history")

            # Find message containing the slack_fingerprint identifier
            for message in history["messages"]:
                # Check in message text
                message_text = message.get("text", "")
                
                # Also check in attachments if present (many alert bots use attachments)
                attachments = message.get("attachments", [])
                for attachment in attachments:
                    attachment_text = attachment.get("text", "") + attachment.get("fallback", "")
                    message_text += " " + attachment_text
                
                # Normalize whitespace and case for comparison (remove extra spaces, newlines, tabs)
                normalized_message = " ".join(message_text.split()).lower()
                normalized_fingerprint = " ".join(slack_message_fingerprint.split()).lower()
                
                # Search for fingerprint in combined text (normalized and case-insensitive)
                if normalized_fingerprint in normalized_message:
                    logger.info(f"Found message with fingerprint {slack_message_fingerprint}: ts={message['ts']}")
                    logger.debug(f"Matched message at timestamp: {message['ts']}")
                    return message["ts"]
            
            logger.error(f"No message found with slack_message_fingerprint: {slack_message_fingerprint}")
            return None

        except SlackApiError as e:
            logger.error(f"Slack API error while finding alert message: {e.response['error']}")
            return None

    async def post_threaded_reply(
        self,
        session_id: str,
        slack_message_fingerprint: str,
        analysis: Optional[str] = None,
        error_msg: Optional[str] = None,
        is_pause: bool = False,
    ) -> bool:
        """Reply directly to a message using its ts - no search needed."""

        try:
            message_ts = await self.find_alert_message(
                slack_message_fingerprint=slack_message_fingerprint,
            )
            if not message_ts:
                logger.error(f"Failed to find alert message for session {session_id}")
                return False

            channel_id = self.settings.slack_channel
            message_data = self._format_alert_message(
                session_id=session_id,
                analysis=analysis,
                error_msg=error_msg,
                is_pause=is_pause
            )
            
            await self.client.chat_postMessage(
                channel=channel_id,
                attachments=message_data["attachments"],
                thread_ts=message_ts
            )
            
            logger.info(f"Slack threaded notification sent for session {session_id}")
            return True
        except SlackApiError as e:
            logger.error(f"Failed to send Slack threaded notification for session {session_id}: {e.response['error']}")
            return False

    async def reply_to_chat_directly(
        self,
        analysis: Optional[str] = None,
        error_msg: Optional[str] = None,
        session_id: Optional[str] = None,
        is_pause: bool = False,
    ) -> bool:
        """
        Reply in a chat conversation thread.
        
        Args:
            thread_ts: Thread timestamp to reply to
            message: Chat message content
            session_id: Optional session ID for dashboard link
            is_pause: Whether this is a pause notification (for color coding)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            channel_id = self.settings.slack_channel
            message_data = self._format_alert_message(
                session_id=session_id,
                analysis=analysis,
                error_msg=error_msg,
                is_pause=is_pause
            )
                
            await self.client.chat_postMessage(
                    channel=channel_id,
                    attachments=message_data["attachments"],
            )
            logger.info(f"Slack notification sent for session {session_id}")
            return True
        except SlackApiError as e:
            logger.error(f"Failed to send Slack notification for session {session_id}: {e.response['error']}")
            return False

    def _format_alert_message(
            self,
            session_id: str,
            analysis: Optional[str] = None,
            error_msg: Optional[str] = None,
            is_pause: bool = False,
        ) -> Dict[str, Any]:
            """Format alert message for Slack."""
            text_parts = []

            if analysis:
                text_parts.extend(["*Analysis:*", "", analysis])
            elif error_msg:
                text_parts.extend(["*Error:*", "", error_msg])

            dashboard_url = self.settings.cors_origins[0] if self.settings.cors_origins else "http://localhost:5173"

            text_parts.extend([
                "",
                f"*View Analysis Details:* {dashboard_url}/sessions/{session_id}"
            ])

            # Determine color based on content type
            if error_msg:
                color = "danger"  # Red for errors
            elif is_pause:
                color = "warning"  # Yellow for pauses (needs attention)
            elif analysis:
                color = "good"  # Green for success/start messages
            else:
                color = "warning"  # Yellow fallback

            return {
                "channel": self.settings.slack_channel,
                "attachments": [
                    {
                        "color": color,
                        "text": "\n".join(text_parts),
                        "mrkdwn_in": ["text"]
                    }
                ]
            }
    
    async def close(self):
        """
        Clean up resources.
        """
        if self.client:
            await self.client.close()
