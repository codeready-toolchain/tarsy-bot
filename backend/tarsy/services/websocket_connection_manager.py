"""WebSocket connection manager for real-time event distribution."""

import json
from typing import Dict, Set

from fastapi import WebSocket

from tarsy.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections and channel subscriptions."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        # connection_id -> WebSocket
        self.connections: Dict[str, WebSocket] = {}
        # connection_id -> set of subscribed channels
        self.subscriptions: Dict[str, Set[str]] = {}
        # channel -> set of connection_ids
        self.channel_subscribers: Dict[str, Set[str]] = {}

    async def connect(self, connection_id: str, websocket: WebSocket) -> None:
        """
        Accept WebSocket connection.

        Args:
            connection_id: Unique identifier for this connection
            websocket: WebSocket instance to accept
        """
        await websocket.accept()
        self.connections[connection_id] = websocket
        self.subscriptions[connection_id] = set()
        logger.info(f"WebSocket connected: {connection_id}")

    def disconnect(self, connection_id: str) -> None:
        """
        Remove connection and cleanup subscriptions.

        Args:
            connection_id: Connection to disconnect
        """
        # Unsubscribe from all channels
        if connection_id in self.subscriptions:
            for channel in self.subscriptions[connection_id]:
                if channel in self.channel_subscribers:
                    self.channel_subscribers[channel].discard(connection_id)
                    if not self.channel_subscribers[channel]:
                        del self.channel_subscribers[channel]
            del self.subscriptions[connection_id]

        # Remove connection
        if connection_id in self.connections:
            del self.connections[connection_id]

        logger.info(f"WebSocket disconnected: {connection_id}")

    def subscribe(self, connection_id: str, channel: str) -> None:
        """
        Subscribe connection to channel.

        Args:
            connection_id: Connection to subscribe
            channel: Channel name to subscribe to
        """
        if connection_id not in self.subscriptions:
            logger.warning(f"Cannot subscribe unknown connection {connection_id}")
            return

        self.subscriptions[connection_id].add(channel)

        if channel not in self.channel_subscribers:
            self.channel_subscribers[channel] = set()
        self.channel_subscribers[channel].add(connection_id)

        logger.debug(f"Subscribed {connection_id} to channel '{channel}'")

    def unsubscribe(self, connection_id: str, channel: str) -> None:
        """
        Unsubscribe connection from channel.

        Args:
            connection_id: Connection to unsubscribe
            channel: Channel name to unsubscribe from
        """
        if connection_id in self.subscriptions:
            self.subscriptions[connection_id].discard(channel)

        if channel in self.channel_subscribers:
            self.channel_subscribers[channel].discard(connection_id)
            if not self.channel_subscribers[channel]:
                del self.channel_subscribers[channel]

        logger.debug(f"Unsubscribed {connection_id} from channel '{channel}'")

    async def broadcast_to_channel(self, channel: str, event: dict) -> None:
        """
        Broadcast event to all subscribers of a channel.

        Args:
            channel: Channel to broadcast to
            event: Event data to send
        """
        if channel not in self.channel_subscribers:
            return

        subscribers = list(self.channel_subscribers[channel])
        event_json = json.dumps(event)

        for connection_id in subscribers:
            websocket = self.connections.get(connection_id)
            if websocket:
                try:
                    await websocket.send_text(event_json)
                except Exception as e:
                    logger.error(f"Failed to send to {connection_id}: {e}")
                    # Don't disconnect here - let the WebSocket endpoint handle it

