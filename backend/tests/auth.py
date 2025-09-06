"""Test utilities for JWT authentication testing."""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import jwt
import os
import logging

from tarsy.config.settings import Settings

logger = logging.getLogger(__name__)


def get_test_jwt_service():
    """Get JWT service configured with dev keys (reused for testing)."""
    try:
        from tarsy.services.jwt_service import JWTService
        
        test_settings = Settings()
        # Use absolute paths to avoid working directory issues
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # Go up from backend/tests/ to project root  
        test_settings.jwt_private_key_path = os.path.join(project_root, "keys", "INSECURE-dev-jwt-private-key.pem")
        test_settings.jwt_public_key_path = os.path.join(project_root, "keys", "INSECURE-dev-jwt-public-key.pem")
        test_settings.jwt_algorithm = "RS256"
        test_settings.jwt_issuer = "tarsy-test"
        return JWTService(test_settings)
    except ImportError:
        # Fallback if JWT service not implemented yet
        logger.warning("JWTService not available yet, using mock implementation")
        return None


def create_test_user_token(
    user_id: str = "test_user_123",
    username: str = "test-user", 
    email: str = "test@example.com",
    avatar_url: str = "https://github.com/test.png",
    expired: bool = False
) -> str:
    """Generate test JWT token with custom claims."""
    # Try to use JWT service if available
    jwt_service = get_test_jwt_service()
    
    if jwt_service and not expired:
        return jwt_service.create_user_jwt_token(user_id, username, email, avatar_url)
    
    # Fallback: create token manually for testing
    try:
        from cryptography.hazmat.primitives import serialization
        
        # Load dev private key - use absolute path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # Go up from backend/tests/ to project root
        private_key_path = os.path.join(project_root, "keys", "INSECURE-dev-jwt-private-key.pem")
        if not os.path.exists(private_key_path):
            raise FileNotFoundError(f"Dev private key not found at {private_key_path}")
            
        with open(private_key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        logger.error(f"Failed to load private key: {e}")
        raise RuntimeError("Cannot create test JWT token without private key")
    
    # Create payload
    now = datetime.utcnow()
    if expired:
        # Create token that expired 1 hour ago for testing
        exp_time = now - timedelta(hours=1)
        iat_time = now - timedelta(hours=2)
    else:
        exp_time = now + timedelta(hours=168)  # 1 week
        iat_time = now
    
    payload = {
        "sub": user_id,
        "username": username,
        "email": email,
        "avatar_url": avatar_url,
        "iss": "tarsy-test",
        "iat": int(iat_time.timestamp()),
        "exp": int(exp_time.timestamp())
    }
    
    return jwt.encode(payload, private_key, algorithm="RS256")


def create_test_service_token(
    service_name: str = "test-service"
) -> str:
    """Generate test service account JWT token."""
    # Try to use JWT service if available
    jwt_service = get_test_jwt_service()
    
    if jwt_service:
        return jwt_service.create_service_account_jwt_token(service_name)
    
    # Fallback: create token manually for testing
    try:
        from cryptography.hazmat.primitives import serialization
        
        # Load dev private key - use absolute path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # Go up from backend/tests/ to project root
        private_key_path = os.path.join(project_root, "keys", "INSECURE-dev-jwt-private-key.pem")
        if not os.path.exists(private_key_path):
            raise FileNotFoundError(f"Dev private key not found at {private_key_path}")
            
        with open(private_key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        logger.error(f"Failed to load private key: {e}")
        raise RuntimeError("Cannot create test JWT token without private key")
    
    # Create payload (no expiration for service accounts)
    now = datetime.utcnow()
    payload = {
        "sub": f"service_account:{service_name}",
        "service_account": True,
        "iss": "tarsy-test", 
        "iat": int(now.timestamp())
        # No expiration for service accounts
    }
    
    return jwt.encode(payload, private_key, algorithm="RS256")


def decode_test_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode a test JWT token without verification (for testing purposes only)."""
    try:
        # Decode without verification for testing
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except Exception as e:
        logger.error(f"Failed to decode test token: {e}")
        return None


# Test fixtures - these will be created when the dev keys are available
def _create_test_fixtures():
    """Create test token fixtures if keys are available."""
    try:
        return {
            "VALID_TEST_TOKEN": create_test_user_token(),
            "EXPIRED_TEST_TOKEN": create_test_user_token(expired=True),
            "ADMIN_TEST_TOKEN": create_test_user_token("admin_123", "test-admin", "admin@example.com"),
            "SERVICE_TEST_TOKEN": create_test_service_token("monitoring"),
        }
    except Exception as e:
        logger.warning(f"Cannot create test fixtures yet: {e}")
        return {
            "VALID_TEST_TOKEN": None,
            "EXPIRED_TEST_TOKEN": None, 
            "ADMIN_TEST_TOKEN": None,
            "SERVICE_TEST_TOKEN": None,
        }


# Test fixtures (will be None if keys not available yet)
_fixtures = _create_test_fixtures()
VALID_TEST_TOKEN = _fixtures["VALID_TEST_TOKEN"]
EXPIRED_TEST_TOKEN = _fixtures["EXPIRED_TEST_TOKEN"]
ADMIN_TEST_TOKEN = _fixtures["ADMIN_TEST_TOKEN"]
SERVICE_TEST_TOKEN = _fixtures["SERVICE_TEST_TOKEN"]


def refresh_test_fixtures():
    """Refresh test fixtures (useful after dev keys are created)."""
    global VALID_TEST_TOKEN, EXPIRED_TEST_TOKEN, ADMIN_TEST_TOKEN, SERVICE_TEST_TOKEN
    
    _fixtures = _create_test_fixtures()
    VALID_TEST_TOKEN = _fixtures["VALID_TEST_TOKEN"]
    EXPIRED_TEST_TOKEN = _fixtures["EXPIRED_TEST_TOKEN"] 
    ADMIN_TEST_TOKEN = _fixtures["ADMIN_TEST_TOKEN"]
    SERVICE_TEST_TOKEN = _fixtures["SERVICE_TEST_TOKEN"]
    
    return _fixtures


# Utility functions for test assertions
def assert_token_valid(token: str) -> Dict[str, Any]:
    """Assert that a token is valid and return its payload."""
    payload = decode_test_token(token)
    assert payload is not None, "Token should decode successfully"
    assert "sub" in payload, "Token should have 'sub' claim"
    assert "iss" in payload, "Token should have 'iss' claim"
    assert "iat" in payload, "Token should have 'iat' claim"
    return payload


def assert_user_token(token: str, expected_username: str = None) -> Dict[str, Any]:
    """Assert that a token is a valid user token."""
    payload = assert_token_valid(token)
    assert "username" in payload, "User token should have 'username' claim"
    assert "email" in payload, "User token should have 'email' claim"
    assert "exp" in payload, "User token should have 'exp' claim"
    
    if expected_username:
        assert payload["username"] == expected_username, f"Expected username {expected_username}"
        
    return payload


def assert_service_token(token: str, expected_service: str = None) -> Dict[str, Any]:
    """Assert that a token is a valid service account token."""
    payload = assert_token_valid(token)
    assert payload.get("service_account") is True, "Service token should have 'service_account': true"
    assert payload["sub"].startswith("service_account:"), "Service token sub should start with 'service_account:'"
    assert "exp" not in payload, "Service token should not have expiration"
    
    if expected_service:
        expected_sub = f"service_account:{expected_service}"
        assert payload["sub"] == expected_sub, f"Expected service sub {expected_sub}"
        
    return payload
