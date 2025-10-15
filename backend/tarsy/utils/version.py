"""Version utility for reading application version."""

import os
from pathlib import Path

from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


def get_version() -> str:
    """
    Get the application version.
    
    In production (container), reads from VERSION file injected at build time.
    In development, returns 'dev' or checks environment variable.
    
    Returns:
        Version string (commit SHA or 'dev')
    """
    # Check environment variable first (set in Dockerfile)
    version = os.getenv("APP_VERSION")
    if version:
        return version
    
    # Try reading VERSION file (created during Docker build)
    version_file = Path(__file__).parent.parent / "VERSION"
    if version_file.exists():
        try:
            return version_file.read_text().strip()
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(
                f"Failed to read VERSION file at {version_file}: {type(e).__name__}: {e}"
            )
    
    # Development fallback
    return "dev"


# Module-level version constant
VERSION: str = get_version()

