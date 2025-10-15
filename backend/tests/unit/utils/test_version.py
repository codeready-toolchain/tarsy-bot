"""Tests for version utility."""

import os
from unittest.mock import patch

import pytest

from tarsy.utils.version import get_version


@pytest.mark.unit
class TestVersionUtility:
    """Test version utility - simple and practical tests only."""

    def test_get_version_from_env_variable(self) -> None:
        """Test version is read from APP_VERSION environment variable."""
        with patch.dict(os.environ, {"APP_VERSION": "abc1234"}):
            version = get_version()
            assert version == "abc1234"

    def test_get_version_from_file(self) -> None:
        """Test version is read from VERSION file when env var not set."""
        mock_file_content = "def5678\n"
        
        with (
            patch.dict(os.environ, {}, clear=True),  # Clear APP_VERSION
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=mock_file_content),
        ):
            version = get_version()
            assert version == "def5678"  # Should strip whitespace

    def test_get_version_fallback_to_dev(self) -> None:
        """Test version falls back to 'dev' when neither env var nor file available."""
        with (
            patch.dict(os.environ, {}, clear=True),  # Clear APP_VERSION
            patch("pathlib.Path.exists", return_value=False),
        ):
            version = get_version()
            assert version == "dev"

    def test_get_version_file_read_error(self) -> None:
        """Test version falls back to 'dev' when file read fails."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", side_effect=OSError("Read error")),
        ):
            version = get_version()
            assert version == "dev"

    def test_get_version_priority_env_over_file(self) -> None:
        """Test APP_VERSION environment variable takes priority over file."""
        with (
            patch.dict(os.environ, {"APP_VERSION": "env-version"}),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="file-version"),
        ):
            version = get_version()
            assert version == "env-version"

