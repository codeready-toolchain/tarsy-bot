"""System-level API endpoints."""

from typing import List

from fastapi import APIRouter

from tarsy.models.system_models import SystemWarning
from tarsy.services.system_warnings_service import get_warnings_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/warnings", response_model=List[SystemWarning])
async def get_system_warnings() -> List[SystemWarning]:
    """
    Get active system warnings.

    Returns warnings about non-fatal system errors that operators
    should be aware of (e.g., failed MCP servers, missing configuration).

    Returns:
        List of active system warnings
    """
    warnings_service = get_warnings_service()
    return warnings_service.get_warnings()  # Pydantic handles serialization
