"""WebSocket controller for real-time event streaming."""

import json
import uuid
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tarsy.database.init_db import get_async_session_factory
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.base import AsyncCallback
from tarsy.services.events.manager import get_event_system
from tarsy.services.websocket_connection_manager import WebSocketConnectionManager
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)

websocket_router = APIRouter(prefix="/api/v1", tags=["websocket"])

# Global connection manager
connection_manager = WebSocketConnectionManager()


@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time event streaming.

    Protocol:
    - Client sends: {"action": "subscribe", "channel": "sessions"}
    - Client sends: {"action": "unsubscribe", "channel": "sessions"}
    - Client sends: {"action": "catchup", "channel": "sessions", "last_event_id": 42}
    - Server sends: {"type": "session.started", "session_id": "...", ...}

    Event Flow Integration:
    1. Client subscribes to channel (e.g., "sessions")
    2. WebSocket registers callback with EventListener for that channel
    3. When DB event occurs (PostgreSQL NOTIFY or SQLite poll):
       - EventListener receives notification
       - EventListener calls our registered callback
       - Callback broadcasts event to all WebSocket clients on that channel
    4. WebSocket clients receive event in real-time
    """
    connection_id = str(uuid.uuid4())

    await connection_manager.connect(connection_id, websocket)

    # Track event listener callbacks for this connection
    # Maps channel -> callback function
    subscribed_callbacks: Dict[str, AsyncCallback] = {}

    try:
        # Send connection confirmation
        await websocket.send_json(
            {"type": "connection.established", "connection_id": connection_id}
        )

        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)

            action = message.get("action")
            channel = message.get("channel")

            if action == "subscribe" and channel:
                # Skip if already subscribed
                if channel in subscribed_callbacks:
                    logger.debug(
                        f"Client {connection_id} already subscribed to '{channel}'"
                    )
                    continue

                # 1. Subscribe connection to channel (tracking)
                connection_manager.subscribe(connection_id, channel)

                # 2. Register callback with EventListener (THIS IS THE KEY INTEGRATION!)
                # When PostgreSQL NOTIFY or SQLite polling detects an event,
                # EventListener will call this callback, which broadcasts via WebSocket
                event_system = get_event_system()
                event_listener = event_system.get_listener()

                # Create callback that broadcasts to channel
                # Use closure to capture channel value correctly
                def make_callback(ch: str) -> AsyncCallback:
                    async def callback(event: dict) -> None:
                        # This is called by EventListener when DB event occurs
                        await connection_manager.broadcast_to_channel(ch, event)

                    return callback

                callback = make_callback(channel)
                await event_listener.subscribe(channel, callback)
                subscribed_callbacks[channel] = callback

                await websocket.send_json(
                    {"type": "subscription.confirmed", "channel": channel}
                )
                logger.debug(
                    f"Client {connection_id} subscribed to '{channel}' "
                    f"(registered with EventListener)"
                )

            elif action == "unsubscribe" and channel:
                # Unsubscribe from channel
                connection_manager.unsubscribe(connection_id, channel)

                # Remove EventListener callback
                if channel in subscribed_callbacks:
                    event_system = get_event_system()
                    event_listener = event_system.get_listener()
                    await event_listener.unsubscribe(
                        channel, subscribed_callbacks[channel]
                    )
                    del subscribed_callbacks[channel]
                    logger.debug(
                        f"Client {connection_id} unsubscribed from '{channel}' "
                        f"(removed from EventListener)"
                    )

                await websocket.send_json(
                    {"type": "subscription.cancelled", "channel": channel}
                )

            elif action == "catchup" and channel:
                # Send missed events from database
                last_event_id = message.get("last_event_id", 0)

                async_session_factory = get_async_session_factory()
                async with async_session_factory() as session:
                    event_repo = EventRepository(session)
                    missed_events = await event_repo.get_events_after(
                        channel=channel, after_id=last_event_id, limit=100
                    )

                    for event in missed_events:
                        # Inject event id into payload so clients can track last_event_id
                        enriched_payload = {**event.payload, "id": event.id}
                        await websocket.send_json(enriched_payload)

                    logger.debug(
                        f"Sent {len(missed_events)} catchup events to {connection_id}"
                    )

            elif action == "ping":
                # Keepalive
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"Client {connection_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}", exc_info=True)
    finally:
        # Cleanup: Unsubscribe all callbacks from EventListener
        # Use try/except to ensure disconnect() always runs even if event system fails
        try:
            event_system = get_event_system()
            event_listener = event_system.get_listener()
            for channel, callback in subscribed_callbacks.items():
                await event_listener.unsubscribe(channel, callback)
                logger.debug(f"Cleaned up EventListener callback for '{channel}'")
        except Exception as e:
            logger.warning(
                f"Failed to unsubscribe EventListener callbacks during cleanup "
                f"for {connection_id}: {e}"
            )

        # Remove from connection manager (always runs)
        connection_manager.disconnect(connection_id)

