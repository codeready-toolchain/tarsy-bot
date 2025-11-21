"""
Slack Notification Service

Handles sending notifications to Slack channel for alert processing events.
Supports webhooks and provides formatted messages.
"""

from typing import Dict, Any, Optional
import httpx

from tarsy.config.settings import Settings
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class SlackService:
    """
    Service for sending notifications to Slack channels.
    
    Supports:
    - Alert processing completion notifications
    - Alert processing failure notifications  
    - System error notifications
    - Configurable webhook URLs and formatting
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize Slack service with settings.
        
        Args:
            settings: Application settings containing Slack configuration
        """
        self.settings = settings
        
        # Create HTTP client for Slack API calls
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={'Content-Type': 'application/json'}
        )
        
        # Check if Slack is configured
        self.enabled = bool(self.settings.slack_webhook_url and self.settings.slack_webhook_url.strip())
        
        if self.enabled:
            logger.info(f"Slack notifications enabled for channel {self.settings.slack_channel}")
        else:
            logger.info("Slack notifications disabled - no webhook URL configured")
    
    async def send_alert_notification(
        self,
        alert_type: str,
        analysis: Optional[str] = None,
        error: Optional[str] = None,
        session_id: Optional[str] = None,
        alert_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send notification for alert processing event.
        
        Args:
            alert_type: Type of alert processed
            analysis: Analysis result (for successful processing)
            error: Error message (for failed processing)
            session_id: Session ID for tracking
            alert_data: Complete alert data for detailed formatting
            
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Slack notifications disabled - skipping")
            return False
        
        try:
            # Format message based on status
            message = self._format_alert_message(
                alert_type=alert_type,
                analysis=analysis,
                error=error,
                session_id=session_id,
                alert_data=alert_data
            )

            # Send to Slack
            success = await self._send_to_slack(message)
            
            if success:
                logger.info(f"Slack notification sent for {alert_type} alert")
            else:
                logger.warning(f"Failed to send Slack notification for {alert_type} alert")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending Slack notification: {str(e)}")
            return False
    
    def _format_alert_message(
        self,
        alert_type: str,
        analysis: Optional[str] = None,
        error: Optional[str] = None,
        session_id: Optional[str] = None,
        alert_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Format alert message for Slack in Alertmanager style.
        
        Args:
            alert_type: Type of alert
            analysis: Analysis result
            error: Error message
            session_id: Session ID
            alert_data: Complete alert data for detailed formatting
            
        Returns:
            Dict containing formatted Slack message
        """
        # Always treat as firing alert
        firing_count = 1
        
        # Build title - always show as firing
        title = f"{firing_count} alert(s) firing"
        
        # Build the main alert text - always show as firing
        text_parts = []
        text_parts.append("🚒 *Firing*:")
        text_parts.append(self._format_alert_details(alert_type, alert_data))
        
        # Add analysis or error if available
        if analysis:
            text_parts.extend(["", "*Analysis:*", analysis])
        elif error:
            text_parts.extend(["", "*Error:*", error])
        
        # Add session link if available
        if session_id:
            # TODO: Make this dynamic based on the environment
            text_parts.extend([
                "",
                f"*View Analysis Details:* http://localhost:5173/sessions/{session_id}"
            ])
        
        alert_text = "\n".join(text_parts)
        
        # Red bar for all alerts
        color = "danger"
        
        # Use attachment format with color bar
        return {
            "channel": self.settings.slack_channel,
            "attachments": [
                {
                    "color": color,
                    "title": title,
                    "text": alert_text,
                    "mrkdwn_in": ["text"]  # Enable markdown in the text field
                }
            ]
        }
    
    def _format_alert_details(
        self, 
        alert_type: str, 
        alert_data: Optional[Dict[str, Any]], 
    ) -> str:
        """
        Format individual alert details in Alertmanager style.
        
        Args:
            alert_type: Type of alert
            alert_data: Alert data dictionary
            
        Returns:
            Formatted alert details string
        """
        if not alert_data:
            alert_data = {}
        
        details = [f"- *Alert*: {alert_type}"]
        
        # Extract standard fields (similar to Prometheus labels/annotations)
        severity = alert_data.get('severity', alert_data.get('level', 'warning'))
        details.append(f"*Severity*: {severity}")
        
        environment = alert_data.get('environment', alert_data.get('env', 'production'))
        details.append(f"*Environment*: {environment}")
        
        cluster = alert_data.get('cluster', alert_data.get('cluster_name', 'unknown'))
        details.append(f"*Cluster*: {cluster}")
        
        # Optional fields
        if 'namespace' in alert_data:
            details.append(f"*Namespace*: {alert_data['namespace']}")
        
        if 'pod' in alert_data or 'pod_name' in alert_data:
            pod_name = alert_data.get('pod', alert_data.get('pod_name'))
            details.append(f"*Pod*: {pod_name}")
        
        # Message from various possible fields
        message_candidates = ['message', 'description', 'summary', 'details']
        for candidate in message_candidates:
            if candidate in alert_data and alert_data[candidate]:
                message = str(alert_data[candidate])
                # Truncate long messages
                if len(message) > 200:
                    message = message[:200] + "..."
                details.append(f"*Message*: {message}")
                break
        
        # Runbook if available
        if 'runbook' in alert_data:
            details.append(f"*Runbook*: {alert_data['runbook']}")
        
        return "\n".join(details)
    
    async def _send_to_slack(self, message: Dict[str, Any]) -> bool:
        """
        Send formatted message to Slack webhook.
        
        Args:
            message: Formatted Slack message
            
        Returns:
            bool: True if sent successfully
        """
        try:
            response = await self.http_client.post(
                self.settings.slack_webhook_url,
                json=message
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Slack webhook returned status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send to Slack webhook: {str(e)}")
            return False
