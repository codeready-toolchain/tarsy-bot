"""Helper functions for publishing events from sync/async contexts."""

import logging
from typing import Optional

from tarsy.database.init_db import get_async_session_factory
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.event_models import (
    ChatCreatedEvent,
    ChatUserMessageEvent,
    LLMInteractionEvent,
    MCPToolCallEvent,
    MCPToolCallStartedEvent,
    MCPToolListEvent,
    SessionCancelledEvent,
    SessionCancelRequestedEvent,
    SessionCompletedEvent,
    SessionCreatedEvent,
    SessionFailedEvent,
    SessionPausedEvent,
    SessionResumedEvent,
    SessionStartedEvent,
    StageCompletedEvent,
    StageStartedEvent,
)
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.publisher import publish_event

logger = logging.getLogger(__name__)


async def publish_session_created(session_id: str, alert_type: str) -> None:
    """
    Publish session.created event to both global and session-specific channels.

    Args:
        session_id: Session identifier
        alert_type: Type of alert being processed
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionCreatedEvent(session_id=session_id, alert_type=alert_type)
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info(f"[EVENT] Published session.created to channels: 'sessions' and 'session:{session_id}'")
    except Exception as e:
        logger.warning(f"Failed to publish session.created event: {e}")


async def publish_session_started(session_id: str, alert_type: str) -> None:
    """
    Publish session.started event to both global and session-specific channels.

    Args:
        session_id: Session identifier
        alert_type: Type of alert being processed
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionStartedEvent(session_id=session_id, alert_type=alert_type)
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info(f"[EVENT] Published session.started to channels: 'sessions' and 'session:{session_id}'")
    except Exception as e:
        logger.warning(f"Failed to publish session.started event: {e}")


async def publish_session_completed(session_id: str) -> None:
    """
    Publish session.completed event to both global and session-specific channels.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionCompletedEvent(session_id=session_id, status=AlertSessionStatus.COMPLETED.value)
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info(f"[EVENT] Published session.completed to channels: 'sessions' and 'session:{session_id}'")
    except Exception as e:
        logger.warning(f"Failed to publish session.completed event: {e}")


async def publish_session_failed(session_id: str) -> None:
    """
    Publish session.failed event to both global and session-specific channels.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionFailedEvent(session_id=session_id, status=AlertSessionStatus.FAILED.value)
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info(f"[EVENT] Published session.failed to channels: 'sessions' and 'session:{session_id}'")
    except Exception as e:
        logger.warning(f"Failed to publish session.failed event: {e}")


async def publish_session_paused(session_id: str, pause_metadata: Optional[dict] = None) -> None:
    """
    Publish session.paused event to both global and session-specific channels.

    Args:
        session_id: Session identifier
        pause_metadata: Optional metadata about why session paused
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionPausedEvent(
                session_id=session_id, 
                status=AlertSessionStatus.PAUSED.value,
                pause_metadata=pause_metadata
            )
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info(f"[EVENT] Published session.paused to channels: 'sessions' and 'session:{session_id}'")
    except Exception as e:
        logger.warning(f"Failed to publish session.paused event: {e}")


async def publish_session_resumed(session_id: str) -> None:
    """
    Publish session.resumed event to both global and session-specific channels.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionResumedEvent(session_id=session_id, status=AlertSessionStatus.IN_PROGRESS.value)
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info(f"[EVENT] Published session.resumed to channels: 'sessions' and 'session:{session_id}'")
    except Exception as e:
        logger.warning(f"Failed to publish session.resumed event: {e}")


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


async def publish_mcp_tool_call_started(
    session_id: str,
    communication_id: str,
    server_name: str,
    tool_name: str,
    tool_arguments: dict,
    stage_id: Optional[str] = None,
) -> None:
    """
    Publish mcp.tool_call.started event.

    Args:
        session_id: Session identifier
        communication_id: Communication ID (primary key) for deduplication
        server_name: MCP server name
        tool_name: Tool name
        tool_arguments: Tool arguments
        stage_id: Optional stage execution identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = MCPToolCallStartedEvent(
                session_id=session_id,
                communication_id=communication_id,
                stage_id=stage_id,
                server_name=server_name,
                tool_name=tool_name,
                tool_arguments=tool_arguments,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published mcp.tool_call.started event for {communication_id}")
    except Exception as e:
        logger.warning(f"Failed to publish mcp.tool_call.started event: {e}")


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
    session_id: str, 
    stage_id: str, 
    stage_name: str, 
    chat_id: Optional[str] = None,
    chat_user_message_id: Optional[str] = None,
    chat_user_message_content: Optional[str] = None,
    chat_user_message_author: Optional[str] = None,
    parallel_type: Optional[str] = None,
    expected_parallel_count: Optional[int] = None,
) -> None:
    """
    Publish stage.started event.

    Args:
        session_id: Session identifier
        stage_id: Stage execution identifier
        stage_name: Human-readable stage name
        chat_id: Optional chat ID if this is a chat response stage
        chat_user_message_id: Optional user message ID
        chat_user_message_content: Optional user message content
        chat_user_message_author: Optional user message author
        parallel_type: Optional parallel execution type ('multi_agent' or 'replica')
        expected_parallel_count: Optional expected number of parallel children
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = StageStartedEvent(
                session_id=session_id, 
                stage_id=stage_id, 
                stage_name=stage_name, 
                chat_id=chat_id,
                chat_user_message_id=chat_user_message_id,
                chat_user_message_content=chat_user_message_content,
                chat_user_message_author=chat_user_message_author,
                parallel_type=parallel_type,
                expected_parallel_count=expected_parallel_count,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published stage.started event for {stage_id}")
    except Exception as e:
        logger.warning(f"Failed to publish stage.started event: {e}")


async def publish_stage_completed(
    session_id: str, stage_id: str, stage_name: str, status: str, chat_id: Optional[str] = None
) -> None:
    """
    Publish stage.completed event.

    Args:
        session_id: Session identifier
        stage_id: Stage execution identifier
        stage_name: Human-readable stage name
        status: Stage status (completed/failed/partial)
        chat_id: Optional chat ID if this is a chat response stage
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = StageCompletedEvent(
                session_id=session_id,
                stage_id=stage_id,
                stage_name=stage_name,
                status=status,
                chat_id=chat_id,
            )
            await publish_event(
                session, EventChannel.session_details(session_id), event
            )
            logger.debug(f"Published stage.completed event for {stage_id}")
    except Exception as e:
        logger.warning(f"Failed to publish stage.completed event: {e}")


async def publish_cancel_request(session_id: str) -> None:
    """
    Publish cancellation request to backend pods.

    This is published to the 'cancellations' channel which all pods subscribe to.
    The pod owning the task will cancel it.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionCancelRequestedEvent(session_id=session_id)
            # Publish to cancellations channel (backend-only)
            await publish_event(session, EventChannel.CANCELLATIONS, event)
            logger.info(f"[EVENT] Published session.cancel_requested for {session_id}")
    except Exception as e:
        logger.warning(f"Failed to publish cancel request: {e}")


async def publish_chat_cancel_request(stage_execution_id: str) -> None:
    """
    Publish chat execution cancellation request to backend pods.
    
    Similar to publish_cancel_request but for chat executions.
    Uses stage_execution_id instead of session_id.
    
    This is published to the 'cancellations' channel which all pods subscribe to.
    The pod owning the chat task will cancel it.
    
    Args:
        stage_execution_id: Stage execution identifier for the chat response
    """
    try:
        from tarsy.models.event_models import ChatCancelRequestedEvent
        
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = ChatCancelRequestedEvent(stage_execution_id=stage_execution_id)
            # Publish to cancellations channel (backend-only)
            await publish_event(session, EventChannel.CANCELLATIONS, event)
            logger.info(f"[EVENT] Published chat.cancel_requested for {stage_execution_id}")
    except Exception as e:
        logger.warning(f"Failed to publish chat cancel request: {e}")


async def publish_session_cancelled(session_id: str) -> None:
    """
    Publish cancellation confirmation to clients.

    This updates the UI to show the session as cancelled.
    Published when the task is actually cancelled or after orphan timeout.

    Args:
        session_id: Session identifier
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = SessionCancelledEvent(session_id=session_id, status=AlertSessionStatus.CANCELLED.value)
            # Publish to global 'sessions' channel for dashboard
            await publish_event(session, EventChannel.SESSIONS, event)
            # Also publish to session-specific channel for detail views
            await publish_event(session, f"session:{session_id}", event)
            logger.info("[EVENT] Published session.cancelled to channels")
    except Exception as e:
        logger.warning(f"Failed to publish session.cancelled event: {e}")


async def publish_chat_created(
    session_id: str,
    chat_id: str,
    created_by: str
) -> None:
    """
    Publish chat.created event to session-specific channel.
    
    Args:
        session_id: Session identifier
        chat_id: Chat identifier
        created_by: User who created the chat
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = ChatCreatedEvent(
                session_id=session_id,
                chat_id=chat_id,
                created_by=created_by
            )
            # Publish to session-specific channel (reuse existing subscription)
            await publish_event(session, EventChannel.session_details(session_id), event)
            logger.info(f"[EVENT] Published chat.created for chat {chat_id} to session:{session_id}")
    except Exception as e:
        logger.warning(f"Failed to publish chat.created event: {e}")


async def publish_chat_user_message(
    session_id: str,
    chat_id: str,
    message_id: str,
    content: str,
    author: str
) -> None:
    """
    Publish chat.user_message event to session-specific channel.
    
    Args:
        session_id: Session identifier
        chat_id: Chat identifier
        message_id: Message identifier
        content: Message content
        author: Message author
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            event = ChatUserMessageEvent(
                session_id=session_id,
                chat_id=chat_id,
                message_id=message_id,
                content=content,
                author=author
            )
            # Publish to session-specific channel (reuse existing subscription)
            await publish_event(session, EventChannel.session_details(session_id), event)
            logger.debug(f"Published chat.user_message for message {message_id}")
    except Exception as e:
        logger.warning(f"Failed to publish chat.user_message event: {e}")

