"""Tests for tarsy.utils.logger module."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from tarsy.utils.logger import get_logger, get_module_logger, setup_logging, HealthEndpointFilter


@pytest.mark.unit
class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_with_valid_level_uppercase(self) -> None:
        """Test setup_logging accepts valid uppercase log levels."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging("INFO")
            mock_basic_config.assert_called_once()
            # Check that numeric level is passed
            assert mock_basic_config.call_args[1]["level"] == logging.INFO

    def test_setup_logging_with_valid_level_lowercase(self) -> None:
        """Test setup_logging accepts valid lowercase log levels and converts them."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging("debug")
            mock_basic_config.assert_called_once()
            # Check that numeric level is passed
            assert mock_basic_config.call_args[1]["level"] == logging.DEBUG

    def test_setup_logging_with_valid_level_mixed_case(self) -> None:
        """Test setup_logging accepts valid mixed case log levels."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging("WaRnInG")
            mock_basic_config.assert_called_once()
            # Check that numeric level is passed
            assert mock_basic_config.call_args[1]["level"] == logging.WARNING

    @pytest.mark.parametrize(
        "valid_level,expected_numeric",
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ],
    )
    def test_setup_logging_with_all_valid_levels(
        self, valid_level: str, expected_numeric: int
    ) -> None:
        """Test setup_logging works with all standard log levels."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(valid_level)
            mock_basic_config.assert_called_once()
            assert mock_basic_config.call_args[1]["level"] == expected_numeric

    def test_setup_logging_with_invalid_level(self) -> None:
        """Test setup_logging raises ValueError for invalid log level."""
        with pytest.raises(ValueError, match="Invalid log level: INVALID"):
            setup_logging("INVALID")

    def test_setup_logging_with_invalid_level_lowercase(self) -> None:
        """Test setup_logging raises ValueError for invalid lowercase log level."""
        with pytest.raises(ValueError, match="Invalid log level: foobar"):
            setup_logging("foobar")

    def test_setup_logging_with_empty_string(self) -> None:
        """Test setup_logging raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid log level: "):
            setup_logging("")

    def test_setup_logging_sets_tarsy_logger_level(self) -> None:
        """Test setup_logging sets the tarsy logger level to match."""
        with patch("logging.basicConfig"), patch("logging.getLogger") as mock_get_logger:
            mock_tarsy_logger = MagicMock()
            mock_uvicorn_logger = MagicMock()
            mock_httpx_logger = MagicMock()
            mock_sqlalchemy_logger = MagicMock()
            mock_uvicorn_access_logger = MagicMock()
            mock_uvicorn_error_logger = MagicMock()
            mock_get_logger.side_effect = [
                mock_tarsy_logger, 
                mock_uvicorn_logger,
                mock_httpx_logger,
                mock_sqlalchemy_logger,
                mock_uvicorn_access_logger,
                mock_uvicorn_error_logger
            ]

            setup_logging("ERROR")

            # Verify tarsy logger is set to ERROR level
            mock_tarsy_logger.setLevel.assert_called_once_with(logging.ERROR)
            # Verify uvicorn logger is set to INFO level
            mock_uvicorn_logger.setLevel.assert_called_once_with(logging.INFO)
            # Verify SQLAlchemy logger is set to WARNING level
            mock_sqlalchemy_logger.setLevel.assert_called_once_with(logging.WARNING)

    def test_setup_logging_default_level(self) -> None:
        """Test setup_logging uses INFO as default level."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging()
            mock_basic_config.assert_called_once()
            assert mock_basic_config.call_args[1]["level"] == logging.INFO

    def test_setup_logging_removes_file_handlers(self) -> None:
        """Test setup_logging removes any existing file handlers."""
        # Create mock handlers
        mock_file_handler = MagicMock(spec=logging.FileHandler)
        mock_stream_handler = MagicMock(spec=logging.StreamHandler)

        with (
            patch("logging.basicConfig"),
            patch("logging.root.handlers", [mock_file_handler, mock_stream_handler]),
            patch("logging.root.removeHandler") as mock_remove,
        ):
            setup_logging()
            # Only file handler should be removed
            mock_remove.assert_called_once_with(mock_file_handler)

    def test_setup_logging_uses_force_flag(self) -> None:
        """Test setup_logging uses force=True to override existing configuration."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging("INFO")
            assert mock_basic_config.call_args[1]["force"] is True

    def test_setup_logging_applies_health_endpoint_filter(self) -> None:
        """Test setup_logging applies HealthEndpointFilter to uvicorn.access logger."""
        with (
            patch("logging.basicConfig"),
            patch("logging.getLogger") as mock_get_logger,
        ):
            mock_tarsy_logger = MagicMock()
            mock_uvicorn_logger = MagicMock()
            mock_uvicorn_access_logger = MagicMock()
            
            # Mock getLogger to return different loggers based on name
            def get_logger_side_effect(name: str) -> MagicMock:
                if name == "tarsy":
                    return mock_tarsy_logger
                elif name == "uvicorn":
                    return mock_uvicorn_logger
                elif name == "uvicorn.access":
                    return mock_uvicorn_access_logger
                return MagicMock()
            
            mock_get_logger.side_effect = get_logger_side_effect
            
            setup_logging("INFO")
            
            # Verify that addFilter was called on the uvicorn.access logger
            mock_uvicorn_access_logger.addFilter.assert_called_once()
            
            # Verify that the filter is a HealthEndpointFilter instance
            filter_arg = mock_uvicorn_access_logger.addFilter.call_args[0][0]
            assert isinstance(filter_arg, HealthEndpointFilter)


@pytest.mark.unit
class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_tarsy_prefix(self) -> None:
        """Test get_logger returns logger with tarsy prefix."""
        with patch("logging.getLogger") as mock_get_logger:
            get_logger("tarsy.services.test")
            mock_get_logger.assert_called_once_with("tarsy.services.test")

    def test_get_logger_without_tarsy_prefix(self) -> None:
        """Test get_logger adds tarsy prefix if not present."""
        with patch("logging.getLogger") as mock_get_logger:
            get_logger("services.test")
            mock_get_logger.assert_called_once_with("tarsy.services.test")

    def test_get_logger_returns_logger_instance(self) -> None:
        """Test get_logger returns the logging.Logger instance."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock(spec=logging.Logger)
            mock_get_logger.return_value = mock_logger

            result = get_logger("test")

            assert result == mock_logger


@pytest.mark.unit
class TestGetModuleLogger:
    """Tests for get_module_logger function."""

    def test_get_module_logger_strips_tarsy_prefix(self) -> None:
        """Test get_module_logger strips tarsy. prefix from module name."""
        with patch("logging.getLogger") as mock_get_logger:
            get_module_logger("tarsy.services.test")
            mock_get_logger.assert_called_once_with("tarsy.services.test")

    def test_get_module_logger_without_prefix(self) -> None:
        """Test get_module_logger handles module name without tarsy prefix."""
        with patch("logging.getLogger") as mock_get_logger:
            get_module_logger("services.test")
            mock_get_logger.assert_called_once_with("tarsy.services.test")

    def test_get_module_logger_with_dunder_name(self) -> None:
        """Test get_module_logger works with __name__ style input."""
        with patch("logging.getLogger") as mock_get_logger:
            get_module_logger("tarsy.controllers.alert_controller")
            mock_get_logger.assert_called_once_with("tarsy.controllers.alert_controller")

