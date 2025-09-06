"""
Unit tests for JWT authentication dependencies.

Tests HTTP and WebSocket JWT verification dependencies used to protect endpoints,
including token validation, error handling, and dependency injection scenarios.
"""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from tarsy.auth.dependencies import (
    verify_jwt_token, 
    verify_jwt_token_websocket,
    get_jwt_service
)
from tarsy.services.jwt_service import JWTService
from tarsy.config.settings import Settings


@pytest.fixture
def mock_jwt_service():
    """Create mock JWT service."""
    return Mock(spec=JWTService)


@pytest.fixture
def valid_jwt_payload():
    """Create valid JWT payload for testing."""
    return {
        "sub": "user123",
        "username": "testuser",
        "email": "test@example.com",
        "avatar_url": "https://github.com/testuser.png",
        "iss": "tarsy-test",
        "iat": 1609459200,
        "exp": 1609459800
    }


@pytest.fixture
def service_account_jwt_payload():
    """Create service account JWT payload for testing."""
    return {
        "sub": "service_account:monitoring",
        "service_account": True,
        "iss": "tarsy-test",
        "iat": 1609459200
        # No expiration for service accounts
    }


@pytest.fixture
def mock_http_credentials():
    """Create mock HTTP authorization credentials."""
    return Mock(spec=HTTPAuthorizationCredentials, credentials="valid_jwt_token")


@pytest.mark.unit
class TestHTTPJWTVerification:
    """Test HTTP JWT token verification dependency."""
    
    async def test_verify_jwt_token_success_user_token(self, mock_http_credentials, mock_jwt_service, valid_jwt_payload):
        """Test successful JWT token verification for user token."""
        # Setup mock JWT service
        mock_jwt_service.verify_jwt_token.return_value = valid_jwt_payload
        
        result = await verify_jwt_token(mock_http_credentials, mock_jwt_service)
        
        assert result == valid_jwt_payload
        assert result["sub"] == "user123"
        assert result["username"] == "testuser"
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_jwt_token")
    
    async def test_verify_jwt_token_success_service_account(self, mock_http_credentials, mock_jwt_service, service_account_jwt_payload):
        """Test successful JWT token verification for service account token."""
        # Setup mock JWT service
        mock_jwt_service.verify_jwt_token.return_value = service_account_jwt_payload
        
        result = await verify_jwt_token(mock_http_credentials, mock_jwt_service)
        
        assert result == service_account_jwt_payload
        assert result["sub"] == "service_account:monitoring"
        assert result["service_account"] is True
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_jwt_token")
    
    async def test_verify_jwt_token_invalid_token(self, mock_http_credentials, mock_jwt_service):
        """Test JWT token verification with invalid token."""
        # Setup mock JWT service to raise HTTPException
        mock_jwt_service.verify_jwt_token.side_effect = HTTPException(
            status_code=401, 
            detail="Invalid token: signature invalid"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_http_credentials, mock_jwt_service)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_jwt_token")
    
    async def test_verify_jwt_token_expired_token(self, mock_http_credentials, mock_jwt_service):
        """Test JWT token verification with expired token."""
        # Setup mock JWT service to raise HTTPException for expired token
        mock_jwt_service.verify_jwt_token.side_effect = HTTPException(
            status_code=401, 
            detail="Invalid token: token has expired"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_http_credentials, mock_jwt_service)
        
        assert exc_info.value.status_code == 401
        assert "token has expired" in exc_info.value.detail
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_jwt_token")
    
    async def test_verify_jwt_token_service_error(self, mock_http_credentials, mock_jwt_service):
        """Test JWT token verification with unexpected service error."""
        # Setup mock JWT service to raise non-HTTPException
        mock_jwt_service.verify_jwt_token.side_effect = Exception("Unexpected JWT service error")
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_http_credentials, mock_jwt_service)
        
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token validation failed"
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_jwt_token")


@pytest.mark.unit
class TestWebSocketJWTVerification:
    """Test WebSocket JWT token verification dependency."""
    
    async def test_verify_jwt_token_websocket_success_user_token(self, mock_jwt_service, valid_jwt_payload):
        """Test successful WebSocket JWT token verification for user token."""
        # Setup mock JWT service
        mock_jwt_service.verify_jwt_token.return_value = valid_jwt_payload
        
        result = await verify_jwt_token_websocket("valid_jwt_token", mock_jwt_service)
        
        assert result == valid_jwt_payload
        assert result["sub"] == "user123"
        assert result["username"] == "testuser"
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_jwt_token")
    
    async def test_verify_jwt_token_websocket_success_service_account(self, mock_jwt_service, service_account_jwt_payload):
        """Test successful WebSocket JWT token verification for service account."""
        # Setup mock JWT service
        mock_jwt_service.verify_jwt_token.return_value = service_account_jwt_payload
        
        result = await verify_jwt_token_websocket("service_jwt_token", mock_jwt_service)
        
        assert result == service_account_jwt_payload
        assert result["sub"] == "service_account:monitoring"
        assert result["service_account"] is True
        mock_jwt_service.verify_jwt_token.assert_called_once_with("service_jwt_token")
    
    async def test_verify_jwt_token_websocket_invalid_token(self, mock_jwt_service):
        """Test WebSocket JWT token verification with invalid token."""
        # Setup mock JWT service to raise HTTPException
        mock_jwt_service.verify_jwt_token.side_effect = HTTPException(
            status_code=401, 
            detail="Invalid token: signature invalid"
        )
        
        result = await verify_jwt_token_websocket("invalid_token", mock_jwt_service)
        
        assert result is None  # WebSocket verification returns None on error
        mock_jwt_service.verify_jwt_token.assert_called_once_with("invalid_token")
    
    async def test_verify_jwt_token_websocket_expired_token(self, mock_jwt_service):
        """Test WebSocket JWT token verification with expired token."""
        # Setup mock JWT service to raise HTTPException for expired token
        mock_jwt_service.verify_jwt_token.side_effect = HTTPException(
            status_code=401, 
            detail="Invalid token: token has expired"
        )
        
        result = await verify_jwt_token_websocket("expired_token", mock_jwt_service)
        
        assert result is None  # WebSocket verification returns None on error
        mock_jwt_service.verify_jwt_token.assert_called_once_with("expired_token")
    
    async def test_verify_jwt_token_websocket_service_error(self, mock_jwt_service):
        """Test WebSocket JWT token verification with unexpected service error."""
        # Setup mock JWT service to raise non-HTTPException
        mock_jwt_service.verify_jwt_token.side_effect = Exception("Unexpected JWT service error")
        
        result = await verify_jwt_token_websocket("error_token", mock_jwt_service)
        
        assert result is None  # WebSocket verification returns None on any error
        mock_jwt_service.verify_jwt_token.assert_called_once_with("error_token")


@pytest.mark.unit
class TestDependencyErrorHandling:
    """Test consistent error handling across different dependency functions."""
    
    async def test_error_handling_consistency(self, mock_jwt_service):
        """Test consistent error handling across HTTP vs WebSocket dependencies."""
        # Setup different types of errors
        error_scenarios = [
            HTTPException(401, "Invalid signature"),
            HTTPException(401, "Token expired"), 
            Exception("Service unavailable"),
            ValueError("Invalid format")
        ]
        
        for exception in error_scenarios:
            mock_jwt_service.verify_jwt_token.side_effect = exception
            
            # Test HTTP dependency - should always raise HTTPException
            credentials = Mock(spec=HTTPAuthorizationCredentials, credentials="test_token")
            with pytest.raises(HTTPException) as http_exc_info:
                await verify_jwt_token(credentials, mock_jwt_service)
            
            assert http_exc_info.value.status_code == 401
            
            # Test WebSocket dependency - should always return None
            websocket_result = await verify_jwt_token_websocket("test_token", mock_jwt_service)
            assert websocket_result is None
    
    async def test_token_type_differentiation(self, mock_jwt_service):
        """Test verification of different token types."""
        user_payload = {
            "sub": "user123",
            "username": "testuser",
            "email": "test@example.com",
            "iss": "tarsy-test"
        }
        
        service_payload = {
            "sub": "service_account:monitoring",
            "service_account": True,
            "iss": "tarsy-test"
        }
        
        # Configure mock to return different payloads for different tokens
        def mock_verify_side_effect(token):
            if token == "user_token":
                return user_payload
            elif token == "service_token":
                return service_payload
            else:
                raise HTTPException(status_code=401, detail="Invalid token")
        
        mock_jwt_service.verify_jwt_token.side_effect = mock_verify_side_effect
        
        # Test user token verification
        user_credentials = Mock(spec=HTTPAuthorizationCredentials, credentials="user_token")
        user_result = await verify_jwt_token(user_credentials, mock_jwt_service)
        assert user_result["username"] == "testuser"
        assert "service_account" not in user_result
        
        # Test service token verification
        service_result = await verify_jwt_token_websocket("service_token", mock_jwt_service)
        assert service_result["service_account"] is True
        
        # Test invalid token (WebSocket - should return None)
        invalid_result = await verify_jwt_token_websocket("invalid_token", mock_jwt_service)
        assert invalid_result is None
        
        # Test invalid token (HTTP - should raise exception)
        invalid_credentials = Mock(spec=HTTPAuthorizationCredentials, credentials="invalid_token")
        with pytest.raises(HTTPException):
            await verify_jwt_token(invalid_credentials, mock_jwt_service)