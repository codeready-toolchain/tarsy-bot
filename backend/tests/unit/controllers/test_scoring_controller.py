"""
Unit tests for ScoringController.

Tests the REST API endpoints for session scoring with mocked services
to ensure proper request/response handling and API contract compliance.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tarsy.controllers.scoring_controller import router
from tarsy.models.constants import ScoringStatus
from tarsy.models.db_models import SessionScore
from tarsy.services.scoring_service import get_scoring_service
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestScoringControllerEndpoints:
    """Test suite for ScoringController API endpoints."""

    @pytest.fixture
    def app(self):
        """Create FastAPI application with scoring router."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_scoring_service(self):
        """Create mock scoring service."""
        service = Mock()
        service.initiate_scoring = AsyncMock()
        service._get_latest_score = AsyncMock()
        return service

    @pytest.fixture
    def sample_score_db(self):
        """Create sample SessionScoreDB for testing."""
        from tarsy.agents.prompts.judges import CURRENT_PROMPT_HASH

        return SessionScore(
            score_id=str(uuid4()),
            session_id="test-session-123",
            prompt_hash=CURRENT_PROMPT_HASH,
            total_score=75,
            score_analysis="**Logical Flow: 20/25**\nGood investigation pattern.",
            missing_tools_analysis="1. **kubectl-logs**: Would provide detailed logs.",
            score_triggered_by="test-user",
            scored_at_us=now_us() - 60000000,  # 60 seconds ago
            status=ScoringStatus.COMPLETED.value,
            started_at_us=now_us() - 60000000,
            completed_at_us=now_us() - 30000000,
            error_message=None,
        )

    def test_post_score_new_scoring_returns_202(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """Test POST /score initiates new scoring and returns 202."""
        # Setup: pending score
        pending_score = sample_score_db
        pending_score.status = ScoringStatus.PENDING.value
        pending_score.total_score = None
        pending_score.score_analysis = None
        pending_score.missing_tools_analysis = None
        pending_score.completed_at_us = None

        mock_scoring_service.initiate_scoring.return_value = pending_score
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score",
            json={"force_rescore": False},
        )

        # Verify
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == ScoringStatus.PENDING.value
        assert data["session_id"] == sample_score_db.session_id
        assert data["total_score"] is None  # Not completed yet

        mock_scoring_service.initiate_scoring.assert_called_once()

    def test_post_score_existing_completed_returns_200(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """Test POST /score returns existing completed score with 200."""
        # Setup: completed score already exists
        mock_scoring_service.initiate_scoring.return_value = sample_score_db
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score",
            json={"force_rescore": False},
        )

        # Verify
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ScoringStatus.COMPLETED.value
        assert data["total_score"] == 75
        assert data["score_analysis"] is not None

    def test_post_score_session_not_found_returns_404(
        self, app, client, mock_scoring_service
    ):
        """Test POST /score returns 404 when session not found."""
        from tarsy.services.scoring_service import SessionNotFoundError

        # Setup: service raises SessionNotFoundError for missing session
        mock_scoring_service.initiate_scoring.side_effect = SessionNotFoundError(
            "Session test-session-999 was not found"
        )
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            "/api/v1/scoring/sessions/test-session-999/score",
            json={"force_rescore": False},
        )

        # Verify
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_post_score_session_not_completed_returns_400(
        self, app, client, mock_scoring_service
    ):
        """Test POST /score returns 400 when session not completed."""
        from tarsy.services.scoring_service import SessionNotCompletedError

        # Setup: service raises SessionNotCompletedError for non-completed session
        mock_scoring_service.initiate_scoring.side_effect = SessionNotCompletedError(
            "Session must be completed (current status: in_progress)"
        )
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            "/api/v1/scoring/sessions/test-session-123/score",
            json={"force_rescore": False},
        )

        # Verify
        assert response.status_code == 400
        assert "must be completed" in response.json()["detail"]

    def test_post_score_force_rescore_conflict_returns_409(
        self, app, client, mock_scoring_service
    ):
        """
        Test POST /score returns 409 when force_rescore conflicts.

        Verifies 409 response when force_rescore conflicts with active scoring.
        """
        # Setup: service raises ValueError for concurrent scoring
        mock_scoring_service.initiate_scoring.side_effect = ValueError(
            "Cannot force rescore while scoring is pending"
        )
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            "/api/v1/scoring/sessions/test-session-123/score",
            json={"force_rescore": True},
        )

        # Verify
        assert response.status_code == 409
        assert "Cannot force rescore while" in response.json()["detail"]

    def test_post_score_force_rescore_creates_new_score(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """Test POST /score with force_rescore=true creates new scoring."""
        # Setup: new pending score for force rescore
        new_score = sample_score_db
        new_score.score_id = str(uuid4())  # Different score_id
        new_score.status = ScoringStatus.PENDING.value
        new_score.total_score = None
        new_score.score_analysis = None
        new_score.missing_tools_analysis = None

        mock_scoring_service.initiate_scoring.return_value = new_score
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score",
            json={"force_rescore": True},
        )

        # Verify
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == ScoringStatus.PENDING.value

        # Verify force_rescore was passed
        mock_scoring_service.initiate_scoring.assert_called_once()
        call_args = mock_scoring_service.initiate_scoring.call_args
        assert call_args.kwargs["force_rescore"] is True

    def test_post_score_database_error_returns_500(
        self, app, client, mock_scoring_service
    ):
        """Test POST /score returns 500 on database error."""
        # Setup: service raises RuntimeError for database error
        mock_scoring_service.initiate_scoring.side_effect = RuntimeError(
            "Database connection failed"
        )
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.post(
            "/api/v1/scoring/sessions/test-session-123/score",
            json={"force_rescore": False},
        )

        # Verify
        assert response.status_code == 500
        assert "Scoring service error" in response.json()["detail"]

    def test_get_score_success_returns_200(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """Test GET /score returns existing score successfully."""
        # Setup
        mock_scoring_service._get_latest_score.return_value = sample_score_db
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.get(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score"
        )

        # Verify
        assert response.status_code == 200
        data = response.json()
        assert data["score_id"] == sample_score_db.score_id
        assert data["session_id"] == sample_score_db.session_id
        assert data["status"] == ScoringStatus.COMPLETED.value
        assert data["total_score"] == 75
        assert data["current_prompt_used"] is True

    def test_get_score_not_found_returns_404(self, app, client, mock_scoring_service):
        """Test GET /score returns 404 when no score exists."""
        # Setup: no score found
        mock_scoring_service._get_latest_score.return_value = None
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.get("/api/v1/scoring/sessions/test-session-999/score")

        # Verify
        assert response.status_code == 404
        assert "No score found" in response.json()["detail"]

    def test_get_score_in_progress_returns_null_fields(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """Test GET /score returns null fields for in-progress scoring."""
        # Setup: in-progress score
        in_progress_score = sample_score_db
        in_progress_score.status = ScoringStatus.IN_PROGRESS.value
        in_progress_score.total_score = None
        in_progress_score.score_analysis = None
        in_progress_score.missing_tools_analysis = None
        in_progress_score.completed_at_us = None

        mock_scoring_service._get_latest_score.return_value = in_progress_score
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.get(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score"
        )

        # Verify
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ScoringStatus.IN_PROGRESS.value
        assert data["total_score"] is None
        assert data["score_analysis"] is None
        assert data["missing_tools_analysis"] is None
        assert data["completed_at_us"] is None

    def test_get_score_failed_includes_error_message(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """Test GET /score includes error_message for failed scoring."""
        # Setup: failed score
        failed_score = sample_score_db
        failed_score.status = ScoringStatus.FAILED.value
        failed_score.error_message = (
            "ValueError: Score not found (expected integer on last line)"
        )
        failed_score.total_score = None
        failed_score.score_analysis = None
        failed_score.missing_tools_analysis = None

        mock_scoring_service._get_latest_score.return_value = failed_score
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.get(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score"
        )

        # Verify
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ScoringStatus.FAILED.value
        assert data["error_message"] is not None
        assert "Score not found" in data["error_message"]
        assert data["total_score"] is None

    def test_get_score_database_error_returns_500(
        self, app, client, mock_scoring_service
    ):
        """Test GET /score returns 500 on database error."""
        # Setup
        mock_scoring_service._get_latest_score.side_effect = RuntimeError(
            "Database connection failed"
        )
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.get("/api/v1/scoring/sessions/test-session-123/score")

        # Verify
        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]

    def test_post_score_default_force_rescore_false(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """
        Test POST /score uses force_rescore=false by default.

        Verifies force_rescore defaults to false when not provided in request.
        """
        # Setup
        mock_scoring_service.initiate_scoring.return_value = sample_score_db
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute without request body
        response = client.post(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score"
        )

        # Verify
        assert response.status_code == 200
        mock_scoring_service.initiate_scoring.assert_called_once()
        call_args = mock_scoring_service.initiate_scoring.call_args
        assert call_args.kwargs["force_rescore"] is False

    def test_score_response_includes_current_prompt_used_field(
        self, app, client, mock_scoring_service, sample_score_db
    ):
        """
        Test score responses include current_prompt_used.

        Verifies score responses include current_prompt_used computed field.
        """
        # Setup
        mock_scoring_service._get_latest_score.return_value = sample_score_db
        app.dependency_overrides[get_scoring_service] = lambda: mock_scoring_service

        # Execute
        response = client.get(
            f"/api/v1/scoring/sessions/{sample_score_db.session_id}/score"
        )

        # Verify
        assert response.status_code == 200
        data = response.json()
        assert "current_prompt_used" in data
        assert isinstance(data["current_prompt_used"], bool)
