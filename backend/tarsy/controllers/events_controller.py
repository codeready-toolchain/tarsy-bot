"""
Events Controller.

FastAPI controller for Server-Sent Events endpoints.
Provides real-time event streaming with catchup support.
"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from tarsy.database.init_db import get_async_session_factory
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.manager import get_event_system
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)

events_router = APIRouter(prefix="/api/v1/events", tags=["events"])


@events_router.get(
    "/stream",
    response_class=StreamingResponse,
    summary="Server-Sent Events Stream",
    description="""
    Subscribe to real-time event stream with automatic catchup support.
    
    **Channels:**
    - `sessions` - Global session lifecycle events
    - `session:{session_id}` - Per-session detail events
    
    **Catchup:**
    - Provide `last_event_id` to receive missed events since last connection
    - Server replays events from database before streaming live events
    
    **Event Format:**
    - Server-Sent Events (SSE) with `id` and `data` fields
    - Clients should track `last_event_id` for reconnection
    """,
)
async def event_stream(
    request: Request, channel: str, last_event_id: int = 0
) -> StreamingResponse:
    """
    Server-Sent Events endpoint with catchup support.

    Args:
        channel: Event channel to subscribe to (required, e.g., 'sessions' or 'session:abc-123')
        last_event_id: Last event ID received (0 for new connection)

    Returns:
        StreamingResponse with text/event-stream media type
    """

    async def event_generator():
        # 1. Catchup: Send missed events from database using repository
        if last_event_id > 0:
            async_session_factory = get_async_session_factory()
            async with async_session_factory() as session:
                event_repo = EventRepository(session)

                # Get missed events (type-safe query)
                missed_events = await event_repo.get_events_after(
                    channel=channel, after_id=last_event_id, limit=100
                )

                logger.info(
                    f"Sending {len(missed_events)} catchup event(s) to client "
                    f"on '{channel}' after ID {last_event_id}"
                )

                for event in missed_events:
                    # Event.payload contains the event dict
                    payload_json = json.dumps(event.payload)

                    yield f"id: {event.id}\n"
                    yield f"data: {payload_json}\n\n"

        # 2. Real-time: Subscribe to live events
        queue = asyncio.Queue()

        async def callback(event: dict):
            await queue.put(event)

        # Get event listener from manager
        event_system = get_event_system()
        event_listener = event_system.get_listener()

        await event_listener.subscribe(channel, callback)
        
        # Send immediate connection confirmation to trigger client onopen
        # Without this, client waits for first event or 30s timeout
        yield ": connected\n\n"
        logger.debug(f"SSE connection established for '{channel}'")

        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.debug(f"Client disconnected from '{channel}' stream")
                    break

                try:
                    # Wait for next event with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30)

                    event_id = event.get("id", 0)
                    payload = json.dumps(event)

                    yield f"id: {event_id}\n"
                    yield f"data: {payload}\n\n"

                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            # Cleanup: Unsubscribe callback from channel
            await event_listener.unsubscribe(channel, callback)
            logger.debug(f"Unsubscribed from channel '{channel}'")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

