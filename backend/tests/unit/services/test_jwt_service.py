"""
Unit tests for JWT authentication service.

Tests JWT token generation, verification, RSA key handling, and error scenarios
for both user and service account authentication.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from contextlib import contextmanager

import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from tarsy.config.settings import Settings


@contextmanager
def real_jwt_service():
    """Context manager to temporarily use the real JWT service instead of mocks."""
    # Save the current mock
    original_module = sys.modules.get('tarsy.services.jwt_service')
    
    try:
        # Remove the mock to allow real import
        if 'tarsy.services.jwt_service' in sys.modules:
            del sys.modules['tarsy.services.jwt_service']
        
        # Import the real module
        import tarsy.services.jwt_service as real_module
        yield real_module.JWTService
        
    finally:
        # Restore the original mock
        if original_module is not None:
            sys.modules['tarsy.services.jwt_service'] = original_module


@pytest.fixture
def test_rsa_keys():
    """Generate temporary RSA key pair for testing."""
    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    
    # Serialize keys to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem, public_pem, private_key, public_key


@pytest.fixture
def test_key_files(test_rsa_keys):
    """Create temporary key files for testing."""
    private_pem, public_pem, _, _ = test_rsa_keys
    
    with tempfile.TemporaryDirectory() as temp_dir:
        private_key_path = Path(temp_dir) / "private.pem"
        public_key_path = Path(temp_dir) / "public.pem"
        
        private_key_path.write_bytes(private_pem)
        public_key_path.write_bytes(public_pem)
        
        yield str(private_key_path), str(public_key_path)


@pytest.fixture
def test_settings(test_key_files):
    """Create test settings with temporary key files."""
    private_key_path, public_key_path = test_key_files
    
    settings = Mock(spec=Settings)
    settings.jwt_private_key_path = private_key_path
    settings.jwt_public_key_path = public_key_path
    settings.jwt_algorithm = "RS256"
    settings.jwt_issuer = "tarsy-test"
    settings.user_token_expiry_hours = 168  # 1 week
    
    return settings


@pytest.fixture
def jwt_service(test_settings):
    """Create JWT service instance with test settings."""
    with real_jwt_service() as JWTService:
        return JWTService(test_settings)


@pytest.mark.unit
class TestJWTServiceInitialization:
    """Test JWT service initialization and key loading."""
    
    def test_successful_initialization(self, test_settings):
        """Test successful JWT service initialization with valid keys."""
        with real_jwt_service() as JWTService:
            service = JWTService(test_settings)
        
        assert service.settings == test_settings
        assert service.algorithm == "RS256"
        assert service.issuer == "tarsy-test"
        assert service.private_key is not None
        assert service.public_key is not None
    
    def test_missing_private_key_file(self, test_settings):
        """Test initialization fails with missing private key file."""
        test_settings.jwt_private_key_path = "/nonexistent/private.pem"
        
        with pytest.raises(FileNotFoundError, match="JWT private key not found"):
            with real_jwt_service() as JWTService:
                JWTService(test_settings)
    
    def test_missing_public_key_file(self, test_settings):
        """Test initialization fails with missing public key file."""
        test_settings.jwt_public_key_path = "/nonexistent/public.pem"
        
        with pytest.raises(FileNotFoundError, match="JWT public key not found"):
            with real_jwt_service() as JWTService:
                JWTService(test_settings)
    
    def test_invalid_private_key_format(self, test_key_files):
        """Test initialization fails with invalid private key format."""
        private_key_path, public_key_path = test_key_files
        
        # Write invalid private key content
        Path(private_key_path).write_text("invalid private key content")
        
        settings = Mock(spec=Settings)
        settings.jwt_private_key_path = private_key_path
        settings.jwt_public_key_path = public_key_path
        
        with pytest.raises(Exception):  # cryptography will raise various exceptions
            with real_jwt_service() as JWTService:
                JWTService(settings)
    
    def test_invalid_public_key_format(self, test_key_files):
        """Test initialization fails with invalid public key format."""
        private_key_path, public_key_path = test_key_files
        
        # Write invalid public key content
        Path(public_key_path).write_text("invalid public key content")
        
        settings = Mock(spec=Settings)
        settings.jwt_private_key_path = private_key_path
        settings.jwt_public_key_path = public_key_path
        
        with pytest.raises(Exception):  # cryptography will raise various exceptions
            with real_jwt_service() as JWTService:
                JWTService(settings)


@pytest.mark.unit
class TestUserJWTTokenGeneration:
    """Test user JWT token creation."""
    
    def test_create_user_jwt_token_valid(self, jwt_service):
        """Test successful user JWT token creation."""
        token = jwt_service.create_user_jwt_token(
            user_id="user123",
            username="testuser",
            email="test@example.com",
            avatar_url="https://github.com/testuser.png"
        )
        
        # Verify token can be decoded (without verification for inspection)
        payload = pyjwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        assert payload["email"] == "test@example.com"
        assert payload["avatar_url"] == "https://github.com/testuser.png"
        assert payload["iss"] == "tarsy-test"
        assert "iat" in payload  # Just check it exists
        assert "exp" in payload  # Just check it exists
        assert payload["exp"] > payload["iat"]  # Expiry should be after issue time
    
    def test_create_user_jwt_token_with_empty_fields(self, jwt_service):
        """Test user JWT token creation with empty optional fields."""
        token = jwt_service.create_user_jwt_token(
            user_id="user123",
            username="testuser",
            email="",
            avatar_url=""
        )
        
        payload = pyjwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        assert payload["email"] == ""
        assert payload["avatar_url"] == ""
    
    def test_create_user_jwt_token_signature_valid(self, jwt_service):
        """Test user JWT token has valid signature."""
        token = jwt_service.create_user_jwt_token(
            user_id="user123",
            username="testuser",
            email="test@example.com",
            avatar_url="https://github.com/testuser.png"
        )
        
        # Should be able to verify with public key
        payload = pyjwt.decode(
            token, 
            jwt_service.public_key, 
            algorithms=["RS256"],
            issuer="tarsy-test"
        )
        
        assert payload["sub"] == "user123"


@pytest.mark.unit
class TestServiceAccountJWTTokenGeneration:
    """Test service account JWT token creation."""
    
    def test_create_service_account_jwt_token_valid(self, jwt_service):
        """Test successful service account JWT token creation."""
        token = jwt_service.create_service_account_jwt_token("monitoring")
        
        # Verify token can be decoded
        payload = pyjwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == "service_account:monitoring"
        assert payload["service_account"] is True
        assert payload["iss"] == "tarsy-test"
        assert "iat" in payload  # Just check it exists
        assert "exp" not in payload  # Service accounts have no expiration
    
    def test_create_service_account_jwt_token_signature_valid(self, jwt_service):
        """Test service account JWT token has valid signature."""
        token = jwt_service.create_service_account_jwt_token("testing")
        
        # Should be able to verify with public key
        payload = pyjwt.decode(
            token, 
            jwt_service.public_key, 
            algorithms=["RS256"],
            issuer="tarsy-test"
        )
        
        assert payload["sub"] == "service_account:testing"
        assert payload["service_account"] is True


@pytest.mark.unit
class TestJWTTokenVerification:
    """Test JWT token verification."""
    
    def test_verify_valid_user_token(self, jwt_service):
        """Test verification of valid user token."""
        token = jwt_service.create_user_jwt_token(
            user_id="user123",
            username="testuser",
            email="test@example.com",
            avatar_url="https://github.com/testuser.png"
        )
        
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        assert payload["email"] == "test@example.com"
        assert payload["avatar_url"] == "https://github.com/testuser.png"
    
    def test_verify_valid_service_account_token(self, jwt_service):
        """Test verification of valid service account token."""
        token = jwt_service.create_service_account_jwt_token("monitoring")
        
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == "service_account:monitoring"
        assert payload["service_account"] is True
    
    def test_verify_invalid_signature(self, jwt_service):
        """Test verification fails with invalid signature."""
        # Create token with different key
        other_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        payload = {
            "sub": "user123",
            "username": "testuser",
            "iss": "tarsy-test",
            "iat": 1609459200
        }
        
        invalid_token = pyjwt.encode(payload, other_private_key, algorithm="RS256")
        
        with pytest.raises(HTTPException) as exc_info:
            jwt_service.verify_jwt_token(invalid_token)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
    
    def test_verify_expired_token(self, jwt_service, test_rsa_keys):
        """Test verification fails with expired token."""
        _, _, private_key, _ = test_rsa_keys
        
        # Create expired token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "iss": "tarsy-test",
            "iat": int(past_time.timestamp()),
            "exp": int(past_time.timestamp())  # Already expired
        }
        
        expired_token = pyjwt.encode(payload, private_key, algorithm="RS256")
        
        with pytest.raises(HTTPException) as exc_info:
            jwt_service.verify_jwt_token(expired_token)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
    
    def test_verify_wrong_issuer(self, jwt_service, test_rsa_keys):
        """Test verification fails with wrong issuer."""
        _, _, private_key, _ = test_rsa_keys
        
        payload = {
            "sub": "user123",
            "username": "testuser",
            "iss": "wrong-issuer",  # Wrong issuer
            "iat": int(datetime.now(timezone.utc).timestamp())
        }
        
        wrong_issuer_token = pyjwt.encode(payload, private_key, algorithm="RS256")
        
        with pytest.raises(HTTPException) as exc_info:
            jwt_service.verify_jwt_token(wrong_issuer_token)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
    
    def test_verify_malformed_token(self, jwt_service):
        """Test verification fails with malformed token."""
        with pytest.raises(HTTPException) as exc_info:
            jwt_service.verify_jwt_token("not.a.jwt.token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
    
    def test_verify_empty_token(self, jwt_service):
        """Test verification fails with empty token."""
        with pytest.raises(HTTPException) as exc_info:
            jwt_service.verify_jwt_token("")
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)


@pytest.mark.unit
class TestJWTServiceEdgeCases:
    """Test edge cases and error scenarios."""
    
    def test_create_token_with_unicode_characters(self, jwt_service):
        """Test token creation with unicode characters."""
        token = jwt_service.create_user_jwt_token(
            user_id="用户123",
            username="tëst-üser",
            email="tëst@éxample.com",
            avatar_url="https://github.com/tëst.png"
        )
        
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == "用户123"
        assert payload["username"] == "tëst-üser"
        assert payload["email"] == "tëst@éxample.com"
    
    def test_create_token_with_long_values(self, jwt_service):
        """Test token creation with very long field values."""
        long_string = "x" * 1000
        
        token = jwt_service.create_user_jwt_token(
            user_id=long_string,
            username=long_string,
            email=f"{long_string}@example.com",
            avatar_url=f"https://github.com/{long_string}.png"
        )
        
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == long_string
        assert payload["username"] == long_string
    
    def test_service_account_name_with_special_characters(self, jwt_service):
        """Test service account token with special characters in name."""
        service_name = "test-service_123"
        
        token = jwt_service.create_service_account_jwt_token(service_name)
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == f"service_account:{service_name}"


@pytest.mark.unit
class TestJWTServiceIntegration:
    """Test integration scenarios with JWT service."""
    
    def test_roundtrip_user_token(self, jwt_service):
        """Test complete roundtrip: create → verify user token."""
        user_data = {
            "user_id": "user123",
            "username": "testuser",
            "email": "test@example.com",
            "avatar_url": "https://github.com/testuser.png"
        }
        
        token = jwt_service.create_user_jwt_token(**user_data)
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == user_data["user_id"]
        assert payload["username"] == user_data["username"]
        assert payload["email"] == user_data["email"]
        assert payload["avatar_url"] == user_data["avatar_url"]
    
    def test_roundtrip_service_account_token(self, jwt_service):
        """Test complete roundtrip: create → verify service account token."""
        service_name = "monitoring-service"
        
        token = jwt_service.create_service_account_jwt_token(service_name)
        payload = jwt_service.verify_jwt_token(token)
        
        assert payload["sub"] == f"service_account:{service_name}"
        assert payload["service_account"] is True
    
    def test_different_jwt_services_incompatible(self, test_rsa_keys):
        """Test that tokens from different JWT services are incompatible."""
        # Create two different JWT services with different keys
        _, _, private_key1, _ = test_rsa_keys
        
        # Generate second key pair
        private_key2 = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create key files for first service
            private_path1 = Path(temp_dir) / "private1.pem"
            public_path1 = Path(temp_dir) / "public1.pem"
            
            private_path1.write_bytes(private_key1.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
            public_path1.write_bytes(private_key1.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
            
            # Create key files for second service
            private_path2 = Path(temp_dir) / "private2.pem"
            public_path2 = Path(temp_dir) / "public2.pem"
            
            private_path2.write_bytes(private_key2.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
            public_path2.write_bytes(private_key2.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
            
            # Create two JWT services
            settings1 = Mock(spec=Settings)
            settings1.jwt_private_key_path = str(private_path1)
            settings1.jwt_public_key_path = str(public_path1)
            settings1.jwt_algorithm = "RS256"
            settings1.jwt_issuer = "service1"
            settings1.user_token_expiry_hours = 168
            
            settings2 = Mock(spec=Settings)
            settings2.jwt_private_key_path = str(private_path2)
            settings2.jwt_public_key_path = str(public_path2)
            settings2.jwt_algorithm = "RS256"
            settings2.jwt_issuer = "service2"
            settings2.user_token_expiry_hours = 168
            
            with real_jwt_service() as JWTService:
                jwt_service1 = JWTService(settings1)
                jwt_service2 = JWTService(settings2)
            
            # Create token with first service
            token = jwt_service1.create_user_jwt_token(
                user_id="user123",
                username="testuser",
                email="test@example.com",
                avatar_url="https://github.com/testuser.png"
            )
            
            # Verify it fails with second service
            with pytest.raises(HTTPException):
                jwt_service2.verify_jwt_token(token)
