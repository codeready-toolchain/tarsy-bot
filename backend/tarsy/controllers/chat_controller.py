"""
Chat Controller

FastAPI controller for chat conversation endpoints.
Provides REST API for creating chats and managing chat messages.
"""

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, Depends

from tarsy.models.api_models import (
    ChatAvailabilityResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatResponse,
    ChatUserMessageListResponse,
    ErrorResponse,
)
from tarsy.services.chat_service import ChatService, get_chat_service
from tarsy.services.history_service import HistoryService, get_history_service
from tarsy.utils.auth_helpers import extract_author_from_request
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Bad request - session not terminated or chat disabled",
        },
        404: {"model": ErrorResponse, "description": "Session not found"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable - shutting down",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Create Chat for Session",
    description="""
    Create a new follow-up chat conversation for a terminated alert processing session.
    
    **Requirements:**
    - Session must exist and be in a terminal state (COMPLETED, FAILED, or CANCELLED)
    - Chain must have chat_enabled=true configuration
    - Only one chat allowed per session (idempotent - returns existing chat if already created)
    
    **Returns:**
    - Chat metadata with chat_id for sending messages
    - Assistant responses will stream via existing session WebSocket channel
    """,
)
async def create_chat(
    request: Request,
    session_id: str = Path(..., description="Session identifier"),
    chat_service: Annotated[ChatService, Depends(get_chat_service)] = None,
    history_service: Annotated[HistoryService, Depends(get_history_service)] = None,
) -> ChatResponse:
    """Create new chat for terminated session."""

    # Check shutdown status (reuse pattern from alert_controller.py)
    from tarsy.main import shutdown_in_progress

    if shutdown_in_progress:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service shutting down",
                "message": "Service is shutting down gracefully. Please retry your request.",
                "retry_after": 30,
            },
        )

    try:
        # Extract author from oauth2-proxy headers
        author = extract_author_from_request(request)

        # Create chat via ChatService (idempotent - returns existing if present)
        chat = await chat_service.create_chat(session_id, author)

        # Get message count
        message_count = await history_service.get_chat_user_message_count(chat.chat_id)

        return ChatResponse(
            chat_id=chat.chat_id,
            session_id=chat.session_id,
            created_at_us=chat.created_at_us,
            created_by=chat.created_by or "unknown",
            message_count=message_count,
        )

    except ValueError as e:
        # ChatService raises ValueError for validation failures
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)

    except Exception as e:
        logger.error(
            f"Failed to create chat for session {session_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to create chat",
                "support_info": "Check server logs or contact support",
            },
        )


@router.get(
    "/sessions/{session_id}/chat-available",
    response_model=ChatAvailabilityResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Check Chat Availability",
    description="""
    Check if follow-up chat is available for a session.
    
    **Returns:**
    - `available: true` if chat can be created/used
    - `available: false` with reason if unavailable
    - `chat_id` if chat already exists
    
    **Availability Criteria:**
    - Session must exist
    - Session must be in a terminal state (COMPLETED, FAILED, or CANCELLED)
    - Chain must have chat_enabled=true
    """,
)
async def check_chat_availability(
    session_id: str = Path(..., description="Session identifier"),
    chat_service: Annotated[ChatService, Depends(get_chat_service)] = None,
    history_service: Annotated[HistoryService, Depends(get_history_service)] = None,
) -> ChatAvailabilityResponse:
    """Check if chat is available for session."""

    try:
        # Check if session exists (get_session is synchronous, wrap in to_thread)
        session = await asyncio.to_thread(history_service.get_session, session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        # Check if chat already exists
        existing_chat = await history_service.get_chat_by_session(session_id)
        if existing_chat:
            return ChatAvailabilityResponse(
                available=True, chat_id=existing_chat.chat_id
            )

        # Check if session is in a terminal state (completed, failed, or cancelled)
        from tarsy.models.constants import AlertSessionStatus
        
        terminal_statuses = AlertSessionStatus.terminal_values()
        if session.status not in terminal_statuses:
            return ChatAvailabilityResponse(
                available=False,
                reason=f"Session must be in a terminal state (current status: {session.status})",
            )

        # Check if chain has chat enabled (delegate to chat_service internal validation)
        # For now, return available=True (chat_service.create_chat will validate chain config)
        return ChatAvailabilityResponse(available=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to check chat availability for {session_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check chat availability: {str(e)}",
        )


@router.get(
    "/chats/{chat_id}",
    response_model=ChatResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Chat not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Chat Details",
    description="Retrieve metadata for a specific chat conversation",
)
async def get_chat(
    chat_id: str = Path(..., description="Chat identifier"),
    history_service: Annotated[HistoryService, Depends(get_history_service)] = None,
) -> ChatResponse:
    """Get chat details by ID."""

    try:
        chat = await history_service.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

        # Get message count
        message_count = await history_service.get_chat_user_message_count(chat_id)

        return ChatResponse(
            chat_id=chat.chat_id,
            session_id=chat.session_id,
            created_at_us=chat.created_at_us,
            created_by=chat.created_by or "unknown",
            message_count=message_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat {chat_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve chat: {str(e)}"
        )


@router.post(
    "/chats/{chat_id}/messages",
    response_model=ChatMessageResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request - invalid message"},
        404: {"model": ErrorResponse, "description": "Chat not found"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable - shutting down",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Send Chat Message",
    description="""
    Send a message to the chat and trigger AI assistant response.
    
    **Request:**
    - Message content (1-10,000 characters)
    
    **Response:**
    - Created user message metadata
    - AI response streams via WebSocket on session:{session_id} channel
    - stage_execution_id links to StageExecution for tracking assistant response
    
    **WebSocket Events:**
    - User message triggers ChatUserMessageEvent
    - AI response streams via existing LLMStreamChunkEvent events
    """,
)
async def send_message(
    request: Request,
    chat_id: str = Path(..., description="Chat identifier"),
    message_request: ChatMessageRequest = None,
    chat_service: Annotated[ChatService, Depends(get_chat_service)] = None,
) -> ChatMessageResponse:
    """Send message to chat - returns immediately, processing in background."""

    # Check shutdown status
    from tarsy.main import shutdown_in_progress

    if shutdown_in_progress:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service shutting down",
                "message": "Service is shutting down gracefully. Please retry your request.",
                "retry_after": 30,
            },
        )

    try:
        # Extract author from oauth2-proxy headers
        author = extract_author_from_request(request)

        # Generate stage_execution_id upfront (like alert submission generates session_id)
        import uuid
        stage_execution_id = str(uuid.uuid4())

        # Get chat and session_id for response
        from tarsy.services.history_service import get_history_service
        history_service = get_history_service()
        chat = await history_service.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

        # Start background processing (matches alert pattern exactly)
        process_callback = request.app.state.process_chat_message_callback

        # Create background task
        task = asyncio.create_task(
            process_callback(chat_id, message_request.content, author, stage_execution_id)
        )

        # Track task for graceful shutdown (matches alert pattern)
        from tarsy.main import active_chat_tasks, active_tasks_lock
        async with active_tasks_lock:
            active_chat_tasks[stage_execution_id] = task

        logger.info(f"Chat message submitted with stage_execution_id: {stage_execution_id}")

        # Return immediately (don't await processing)
        return ChatMessageResponse(
            message_id=stage_execution_id,  # Use execution_id as message tracking ID
            chat_id=chat_id,
            content=message_request.content,
            author=author,
            created_at_us=int(time.time() * 1_000_000),
            stage_execution_id=stage_execution_id,
        )

    except HTTPException:
        raise
    
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)

    except Exception as e:
        logger.error(
            f"Failed to send message to chat {chat_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to process chat message",
                "support_info": "Check server logs or contact support",
            },
        )


@router.get(
    "/chats/{chat_id}/messages",
    response_model=ChatUserMessageListResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Chat not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Chat Message History",
    description="""
    Retrieve user message history for a chat.
    
    **Note:** This returns only user messages. AI responses are tracked via
    StageExecution and LLMInteraction tables (query via session timeline).
    
    **Query Parameters:**
    - limit: Maximum messages to return (default: 50, max: 100)
    - offset: Pagination offset (default: 0)
    """,
)
async def get_chat_messages(
    chat_id: str = Path(..., description="Chat identifier"),
    limit: int = Query(50, ge=1, le=100, description="Maximum messages to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    history_service: Annotated[HistoryService, Depends(get_history_service)] = None,
) -> ChatUserMessageListResponse:
    """Get chat message history."""

    try:
        # Verify chat exists
        chat = await history_service.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

        # Get user messages
        user_messages = await history_service.get_chat_user_messages(
            chat_id=chat_id, limit=limit, offset=offset
        )

        # Get total count
        total_count = await history_service.get_chat_user_message_count(chat_id)

        # Convert to response format
        message_responses = [
            ChatMessageResponse(
                message_id=msg.message_id,
                chat_id=msg.chat_id,
                content=msg.content,
                author=msg.author,
                created_at_us=msg.created_at_us,
                stage_execution_id=None,  # Not stored in ChatUserMessage
            )
            for msg in user_messages
        ]

        return ChatUserMessageListResponse(
            messages=message_responses, total_count=total_count, chat_id=chat_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get messages for chat {chat_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve messages: {str(e)}"
        )

