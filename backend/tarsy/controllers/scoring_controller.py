"""
Scoring Controller

FastAPI controller for session scoring endpoints.
Provides REST API for triggering and retrieving session quality scores
with async background execution pattern.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, Body

from tarsy.models.api_models import SessionScoreResponse, SessionScoreRequest
from tarsy.models.constants import ScoringStatus
from tarsy.models.db_models import SessionScore
from tarsy.services.scoring_service import (
    ScoringService,
    SessionNotCompletedError,
    SessionNotFoundError,
    get_scoring_service,
)
from tarsy.utils.auth_helpers import extract_author_from_request
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/scoring", tags=["scoring"])


def _convert_to_response(score_db: SessionScore) -> SessionScoreResponse:
    """
    Convert database model to API response model.

    Args:
        score_db: SessionScore database model

    Returns:
        SessionScoreResponse
    """
    return SessionScoreResponse(
        score_id=score_db.score_id,
        session_id=score_db.session_id,
        prompt_hash=score_db.prompt_hash,
        total_score=score_db.total_score,
        score_analysis=score_db.score_analysis,
        missing_tools_analysis=score_db.missing_tools_analysis,
        score_triggered_by=score_db.score_triggered_by,
        scored_at_us=score_db.scored_at_us,
        status=score_db.status,
        started_at_us=score_db.started_at_us,
        completed_at_us=score_db.completed_at_us,
        error_message=score_db.error_message,
    )


@router.post(
    "/sessions/{session_id}/score",
    response_model=SessionScoreResponse,
    summary="Score Alert Session",
    description="""
    Trigger async scoring for a session. Returns immediately without blocking.

    **Status tracking:**
    - Poll GET /score endpoint to check completion status

    **Requirements:**
    - Session must be in completed state
    - User attribution from X-Forwarded-User header
    """,
    responses={
        200: {
            "description": "Existing score returned (no new scoring initiated)",
            "model": SessionScoreResponse,
        },
        202: {
            "description": "Scoring is in progress or a new score has been initiated and is in progress",
            "model": SessionScoreResponse,
        },
        400: {
            "description": "Session not in terminal state (must be completed/failed/cancelled)"
        },
        404: {"description": "Session not found"},
        409: {
            "description": "Conflict: force_rescore requested while scoring is in progress"
        },
        500: {"description": "Internal server error"},
    },
)
async def score_session(
    *,
    http_request: Request,
    session_id: str = Path(..., description="Session identifier to score"),
    request: Optional[SessionScoreRequest] = None,
    response: Response,
    scoring_service: Annotated[ScoringService, Depends(get_scoring_service)],
) -> SessionScoreResponse:
    """
    Trigger scoring for a session (async execution).

    Creates a pending score record and launches background scoring task.
    Returns immediately with score_id for tracking progress.

    Args:
        session_id: Session identifier to score
        request: Scoring request with optional force_rescore flag
        scoring_service: Injected scoring service

    Returns:
        SessionScore with status indicating current state

    Raises:
        HTTPException: 400/404/409/500 based on error scenario
    """
    # Extract user from oauth2-proxy headers
    triggered_by = extract_author_from_request(http_request)

    if request is None:
        request = SessionScoreRequest()

    try:
        # Attempt to initiate scoring
        score_db = await scoring_service.initiate_scoring(
            session_id=session_id,
            triggered_by=triggered_by,
            force_rescore=request.force_rescore,
        )

        # Convert to API model
        score = _convert_to_response(score_db)

        # Determine HTTP status code based on score status
        # 202: New scoring initiated (pending/in_progress)
        # 200: Existing score returned (completed/failed)
        if score.status in ScoringStatus.active_values():
            response.status_code = 202
        else:
            response.status_code = 200

        logger.info(
            f"Score request for session {session_id}: "
            f"status={score.status}, score_id={score.score_id}, "
            f"http_status={response.status_code}"
        )

        return score
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SessionNotCompletedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except RuntimeError as e:
        # Database errors
        logger.error(f"Scoring service error for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Scoring service error: {str(e)}"
        ) from e
    except Exception as e:
        # Unexpected errors
        logger.exception(
            f"Unexpected error initiating score for session {session_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        ) from e


@router.get(
    "/sessions/{session_id}/score",
    response_model=SessionScoreResponse,
    summary="Get Session Score",
    description="""
    Retrieve score for a session (any status).

    **Returns:**
    - Complete score details including status
    - Null fields for incomplete scorings (status != completed)
    - Error message for failed scorings

    **Status values:**
    - pending: Scoring queued but not started
    - in_progress: Scoring currently executing
    - completed: Scoring finished successfully
    - failed: Scoring encountered an error
    """,
    responses={
        200: {
            "description": "Score found and returned",
            "model": SessionScoreResponse,
        },
        404: {"description": "Session not found or not yet scored"},
        500: {"description": "Internal server error"},
    },
)
async def get_session_score(
    *,
    session_id: str = Path(..., description="Session identifier"),
    scoring_service: Annotated[ScoringService, Depends(get_scoring_service)],
) -> SessionScoreResponse:
    """
    Retrieve score for a session.

    Args:
        session_id: Session identifier
        scoring_service: Injected scoring service

    Returns:
        SessionScore with current status and results

    Raises:
        HTTPException: 404 if not found, 500 for errors
    """
    try:
        # Get latest score for session
        score_db = await scoring_service._get_latest_score(session_id)

        if not score_db:
            raise HTTPException(
                status_code=404, detail=f"No score found for session {session_id}"
            )

        # Convert to API model
        score = _convert_to_response(score_db)

        logger.debug(
            f"Retrieved score for session {session_id}: "
            f"status={score.status}, score_id={score.score_id}"
        )

        return score

    except HTTPException:
        raise

    except RuntimeError as e:
        # Database errors
        logger.error(
            f"Database error retrieving score for session {session_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") from e

    except Exception as e:
        # Unexpected errors
        logger.exception(
            f"Unexpected error retrieving score for session {session_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        ) from e
