"""Helper functions for publishing events from sync/async contexts."""

import logging
from typing import Optional

from tarsy.database.init_db import get_async_session_factory
from tarsy.models.event_models import (
    SessionCreatedEvent,
    SessionStartedEvent,
    SessionCompletedEvent,
    SessionFailedEvent,
    LLMInteractionEvent,
    MCPToolCallEvent,
    MCPToolListEvent,
    StageStartedEvent,
    StageCompletedEvent,
)
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.publisher import publish_event

logger = logging.getLogger(__name__)


async def publish_session_created(session_id: str, alert_type: str) -> None:
    """
    Publish session.created event.

    Args:
        session_id: Session identifier
        alert_type: Type of alert being processed
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionCreatedEvent(session_id=session_id, alert_type=alert_type)
            await publish_event(session, EventChannel.SESSIONS, event)
            logger.debug(f"Published session.created event for {session_id}")
    except Exception as e:
        logger.warning(f"Failed to publish session.created event: {e}")


async def publish_session_started(session_id: str, alert_type: str) -> None:
    """
    Publish session.started event.

    Args:
        session_id: Session identifier
        alert_type: Type of alert being processed
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionStartedEvent(session_id=session_id, alert_type=alert_type)
            await publish_event(session, EventChannel.SESSIONS, event)
            logger.debug(f"Published session.started event for {session_id}")
    except Exception as e:
        logger.warning(f"Failed to publish session.started event: {e}")


async def publish_session_completed(session_id: str) -> None:
    """
    Publish session.completed event.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionCompletedEvent(session_id=session_id, status="completed")
            await publish_event(session, EventChannel.SESSIONS, event)
            logger.debug(f"Published session.completed event for {session_id}")
    except Exception as e:
        logger.warning(f"Failed to publish session.completed event: {e}")


async def publish_session_failed(session_id: str) -> None:
    """
    Publish session.failed event.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionFailedEvent(session_id=session_id, status="failed")
            await publish_event(session, EventChannel.SESSIONS, event)
            logger.debug(f"Published session.failed event for {session_id}")
    except Exception as e:
        logger.warning(f"Failed to publish session.failed event: {e}")


async def publish_llm_interaction(
    session_id: str, interaction_id: str, stage_id: Optional[str] = None
) -> None:
    """
    Publish llm.interaction event.

    Args:
        session_id: Session identifier
        interaction_id: Interaction identifier
        stage_id: Optional stage execution identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = LLMInteractionEvent(
                session_id=session_id,
                interaction_id=interaction_id,
                stage_id=stage_id,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published llm.interaction event for {interaction_id}")
    except Exception as e:
        logger.warning(f"Failed to publish llm.interaction event: {e}")


async def publish_mcp_tool_call(
    session_id: str,
    interaction_id: str,
    tool_name: str,
    stage_id: Optional[str] = None,
) -> None:
    """
    Publish mcp.tool_call event.

    Args:
        session_id: Session identifier
        interaction_id: Interaction identifier
        tool_name: Name of MCP tool called
        stage_id: Optional stage execution identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = MCPToolCallEvent(
                session_id=session_id,
                interaction_id=interaction_id,
                tool_name=tool_name,
                stage_id=stage_id,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published mcp.tool_call event for {interaction_id}")
    except Exception as e:
        logger.warning(f"Failed to publish mcp.tool_call event: {e}")


async def publish_mcp_tool_list(
    session_id: str,
    request_id: str,
    server_name: Optional[str] = None,
    stage_id: Optional[str] = None,
) -> None:
    """
    Publish mcp.tool_list event.

    Args:
        session_id: Session identifier
        request_id: Request identifier
        server_name: Optional MCP server name
        stage_id: Optional stage execution identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = MCPToolListEvent(
                session_id=session_id,
                request_id=request_id,
                server_name=server_name,
                stage_id=stage_id,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published mcp.tool_list event for {request_id}")
    except Exception as e:
        logger.warning(f"Failed to publish mcp.tool_list event: {e}")


async def publish_stage_started(
    session_id: str, stage_id: str, stage_name: str
) -> None:
    """
    Publish stage.started event.

    Args:
        session_id: Session identifier
        stage_id: Stage execution identifier
        stage_name: Human-readable stage name
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = StageStartedEvent(
                session_id=session_id, stage_id=stage_id, stage_name=stage_name
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published stage.started event for {stage_id}")
    except Exception as e:
        logger.warning(f"Failed to publish stage.started event: {e}")


async def publish_stage_completed(
    session_id: str, stage_id: str, stage_name: str, status: str
) -> None:
    """
    Publish stage.completed event.

    Args:
        session_id: Session identifier
        stage_id: Stage execution identifier
        stage_name: Human-readable stage name
        status: Stage status (completed/failed)
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = StageCompletedEvent(
                session_id=session_id,
                stage_id=stage_id,
                stage_name=stage_name,
                status=status,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published stage.completed event for {stage_id}")
    except Exception as e:
        logger.warning(f"Failed to publish stage.completed event: {e}")

