"""Authentication fixtures for testing with JWT tokens."""

from typing import Dict, Any
from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient

# Use relative import to the auth utilities we moved 
from tests.auth import (
    create_test_user_token, 
    create_test_service_token,
    VALID_TEST_TOKEN,
    ADMIN_TEST_TOKEN,
    SERVICE_TEST_TOKEN,
    refresh_test_fixtures
)


@pytest.fixture
def valid_jwt_token() -> str:
    """Generate a valid JWT token for testing."""
    try:
        return create_test_user_token()
    except Exception:
        # Return a mock token if keys aren't available yet
        return "mock_jwt_token"


@pytest.fixture
def admin_jwt_token() -> str:
    """Generate an admin JWT token for testing."""
    try:
        return create_test_user_token("admin_123", "test-admin", "admin@example.com")
    except Exception:
        return "mock_admin_jwt_token"


@pytest.fixture
def service_jwt_token() -> str:
    """Generate a service account JWT token for testing."""
    try:
        return create_test_service_token("test-service")
    except Exception:
        return "mock_service_jwt_token"


@pytest.fixture
def auth_headers(valid_jwt_token: str) -> Dict[str, str]:
    """Generate authentication headers with Bearer token."""
    return {"Authorization": f"Bearer {valid_jwt_token}"}


@pytest.fixture
def admin_auth_headers(admin_jwt_token: str) -> Dict[str, str]:
    """Generate admin authentication headers with Bearer token."""
    return {"Authorization": f"Bearer {admin_jwt_token}"}


@pytest.fixture
def service_auth_headers(service_jwt_token: str) -> Dict[str, str]:
    """Generate service account authentication headers."""
    return {"Authorization": f"Bearer {service_jwt_token}"}


class AuthenticatedTestClient:
    """Wrapper around TestClient that automatically includes JWT authentication."""
    
    def __init__(self, client: TestClient, auth_headers: Dict[str, str]):
        self.client = client
        self.auth_headers = auth_headers
    
    def get(self, url: str, **kwargs):
        """GET request with authentication headers."""
        headers = kwargs.pop('headers', {})
        headers.update(self.auth_headers)
        return self.client.get(url, headers=headers, **kwargs)
    
    def post(self, url: str, **kwargs):
        """POST request with authentication headers."""
        headers = kwargs.pop('headers', {})
        headers.update(self.auth_headers)
        return self.client.post(url, headers=headers, **kwargs)
    
    def put(self, url: str, **kwargs):
        """PUT request with authentication headers."""
        headers = kwargs.pop('headers', {})
        headers.update(self.auth_headers)
        return self.client.put(url, headers=headers, **kwargs)
    
    def delete(self, url: str, **kwargs):
        """DELETE request with authentication headers."""
        headers = kwargs.pop('headers', {})
        headers.update(self.auth_headers)
        return self.client.delete(url, headers=headers, **kwargs)
    
    def patch(self, url: str, **kwargs):
        """PATCH request with authentication headers."""
        headers = kwargs.pop('headers', {})
        headers.update(self.auth_headers)
        return self.client.patch(url, headers=headers, **kwargs)


@pytest.fixture
def authenticated_client(client: TestClient, auth_headers: Dict[str, str]) -> AuthenticatedTestClient:
    """Create authenticated test client with JWT token."""
    return AuthenticatedTestClient(client, auth_headers)


@pytest.fixture 
def admin_authenticated_client(client: TestClient, admin_auth_headers: Dict[str, str]) -> AuthenticatedTestClient:
    """Create authenticated test client with admin JWT token."""
    return AuthenticatedTestClient(client, admin_auth_headers)


@pytest.fixture
def service_authenticated_client(client: TestClient, service_auth_headers: Dict[str, str]) -> AuthenticatedTestClient:
    """Create authenticated test client with service account JWT token."""
    return AuthenticatedTestClient(client, service_auth_headers)


@pytest.fixture
def mock_jwt_verification():
    """Mock JWT verification to bypass actual JWT validation in tests."""
    mock_payload = {
        "sub": "test_user_123",
        "username": "test-user",
        "email": "test@example.com", 
        "avatar_url": "https://github.com/test.png",
        "iss": "tarsy-test",
        "iat": 1234567890,
        "exp": 1234567890 + 3600
    }
    
    with patch('tarsy.auth.dependencies.verify_jwt_token') as mock_verify:
        mock_verify.return_value = mock_payload
        yield mock_verify


@pytest.fixture
def mock_service_jwt_verification():
    """Mock JWT verification for service account tokens."""
    mock_payload = {
        "sub": "service_account:test-service",
        "service_account": True,
        "iss": "tarsy-test",
        "iat": 1234567890
        # No exp for service accounts
    }
    
    with patch('tarsy.auth.dependencies.verify_jwt_token') as mock_verify:
        mock_verify.return_value = mock_payload
        yield mock_verify


@pytest.fixture
def mock_jwt_websocket_verification():
    """Mock JWT verification for WebSocket endpoints."""
    mock_payload = {
        "sub": "test_user_123",
        "username": "test-user",
        "email": "test@example.com",
        "avatar_url": "https://github.com/test.png",
        "iss": "tarsy-test",
        "iat": 1234567890,
        "exp": 1234567890 + 3600
    }
    
    with patch('tarsy.auth.dependencies.verify_jwt_token_websocket') as mock_verify:
        mock_verify.return_value = mock_payload
        yield mock_verify
