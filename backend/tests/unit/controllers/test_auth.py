"""
Unit tests for authentication controllers.

Tests comprehensive authentication functionality including:
- GitHub OAuth login and callback flows
- Hybrid authentication (Bearer tokens + HTTP-only cookies) 
- Authentication endpoints (logout, token helper)
- State parameter encoding/decoding
- Redirect URL validation
"""

from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException, Response
from fastapi.responses import RedirectResponse

from tarsy.controllers.auth import github_login, github_callback, logout, get_token_from_cookie
from tarsy.auth.dependencies import verify_jwt_token
from tarsy.repositories.oauth_state_repository import OAuthStateRepository
import json
import base64


def encode_oauth_state(csrf_token: str, redirect_url: str) -> str:
    """Helper function to encode OAuth state like the actual controller does."""
    state_data = {
        "csrf_token": csrf_token,
        "redirect_url": redirect_url
    }
    return base64.urlsafe_b64encode(
        json.dumps(state_data).encode()
    ).decode()


@pytest.fixture
def mock_session():
    """Mock database session."""
    return Mock()


@pytest.fixture
def mock_response():
    """Mock FastAPI Response object."""
    return Mock(spec=Response)


@pytest.fixture  
def mock_settings_dev():
    """Mock settings for development mode."""
    settings = Mock()
    settings.dev_mode = True
    return settings


@pytest.fixture
def mock_settings_production():
    """Mock settings for production mode."""
    settings = Mock()
    settings.dev_mode = False
    settings.github_client_id = "prod_client_id"
    settings.github_client_secret = "prod_client_secret"
    settings.github_callback_url = "https://api.example.com/auth/callback"
    settings.oauth_state_ttl_minutes = 10
    settings.frontend_url = "http://localhost:5173"  # Add missing frontend_url
    settings.backend_url = "http://localhost:8000"  # Add missing backend_url
    return settings


@pytest.fixture  
def mock_settings_hybrid():
    """Mock settings for hybrid authentication."""
    settings = Mock()
    settings.dev_mode = False
    settings.frontend_url = "http://localhost:5173"
    settings.cookie_domain = None
    settings.oauth_state_ttl_minutes = 10  # Add numeric value
    settings.github_client_id = "test_client_id"
    settings.github_client_secret = "test_client_secret"
    settings.github_callback_url = "http://localhost:8000/auth/callback"
    settings.github_base_url = "https://api.github.com"
    return settings


@pytest.mark.unit
class TestGithubLoginEndpoint:
    """Test GitHub OAuth login endpoint."""
    
    @patch('tarsy.controllers.auth.get_settings')
    async def test_github_login_dev_mode(
        self, 
        mock_get_settings,
        mock_session,
        mock_settings_dev
    ):
        """Test GitHub login in development mode bypasses OAuth."""
        mock_get_settings.return_value = mock_settings_dev
        
        result = await github_login(mock_session, redirect_url="http://localhost:5173/")
        
        assert isinstance(result, RedirectResponse)
        assert "/auth/callback?code=dev_fake_code&state=" in str(result.headers['location'])
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository')
    @patch('tarsy.controllers.auth.uuid4')
    @patch('tarsy.controllers.auth.now_us')
    async def test_github_login_production_mode(
        self, 
        mock_now_us,
        mock_uuid4,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_session,
        mock_settings_production
    ):
        """Test GitHub login production mode creates OAuth state and redirects."""
        mock_get_settings.return_value = mock_settings_production
        mock_now_us.return_value = 1609459200_000_000  # 2021-01-01 00:00:00 UTC
        mock_uuid4.return_value = "test_state_123"
        
        # Mock OAuth state repository
        mock_oauth_repo = Mock(spec=OAuthStateRepository)
        mock_oauth_repo_class.return_value = mock_oauth_repo
        
        # Skip complex OAuth client mocking - focus on our business logic
        with patch('builtins.__import__') as mock_import:
            # Mock minimal authlib behavior
            def import_side_effect(name, *args, **kwargs):
                if name == 'authlib.integrations.httpx_client':
                    mock_module = Mock()
                    mock_client = Mock()
                    mock_client.return_value.create_authorization_url.return_value = (
                        "https://github.com/login/oauth/authorize?client_id=prod_client_id&state=test_state_123",
                        "test_state_123"
                    )
                    mock_module.AsyncOAuth2Client = mock_client
                    return mock_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = await github_login(mock_session, redirect_url="http://localhost:5173/")
            
            # Test our business logic: OAuth state creation with correct expiration
            mock_oauth_repo.create_state.assert_called_once_with(
                "test_state_123",
                1609459200_000_000 + (10 * 60_000_000)  # TTL in microseconds
            )
            
            # Verify redirect behavior
            assert isinstance(result, RedirectResponse)
            assert "github.com/login/oauth/authorize" in str(result.headers['location'])
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository')
    async def test_github_login_oauth_state_creation_error(
        self,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_session,
        mock_settings_production
    ):
        """Test GitHub login handles OAuth state creation errors."""
        mock_get_settings.return_value = mock_settings_production
        
        # Mock OAuth state repository to raise exception
        mock_oauth_repo = Mock(spec=OAuthStateRepository)
        mock_oauth_repo.create_state.side_effect = Exception("Database error")
        mock_oauth_repo_class.return_value = mock_oauth_repo
        
        with pytest.raises(Exception, match="Database error"):
            await github_login(mock_session, redirect_url="http://localhost:5173/")


@pytest.mark.unit
class TestGithubCallbackEndpoint:
    """Test GitHub OAuth callback endpoint."""
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.JWTService')
    @patch('tarsy.controllers.auth._set_auth_cookie')
    async def test_github_callback_dev_mode(
        self,
        mock_set_auth_cookie,
        mock_jwt_service_class,
        mock_get_settings,
        mock_session,
        mock_response,
        mock_settings_dev
    ):
        """Test GitHub callback in development mode."""
        mock_get_settings.return_value = mock_settings_dev
        
        # Mock JWT service
        mock_jwt_service = Mock()
        mock_jwt_service_class.return_value = mock_jwt_service
        mock_jwt_service.create_user_jwt_token.return_value = "dev_jwt_token"
        
        # Create properly encoded state for dev mode
        encoded_state = encode_oauth_state("dev_fake_state", "http://localhost:5173/")
        
        result = await github_callback(
            code="dev_fake_code",
            state=encoded_state,
            response=mock_response,
            session=mock_session
        )
        
        # Verify JWT token was created with actual dev user
        mock_jwt_service.create_user_jwt_token.assert_called_once_with(
            user_id="999999",
            username="tarsy-dev-user",
            email="dev@tarsy-local.invalid",
            avatar_url="https://github.com/github.png"
        )
        
        # Dev mode sets cookie and redirects
        assert isinstance(result, RedirectResponse)
        # Verify the result is a RedirectResponse with the correct location
        assert result.status_code == 307
        assert result.headers["location"] == "http://localhost:5173/"
        
        # Verify _set_auth_cookie was called with the RedirectResponse and JWT token
        mock_set_auth_cookie.assert_called_once()
        call_args = mock_set_auth_cookie.call_args
        assert call_args[0][0] == result  # First arg should be the RedirectResponse
        assert call_args[0][1] == "dev_jwt_token"  # Second arg should be the JWT token
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository')
    async def test_github_callback_invalid_oauth_state(
        self,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_session,
        mock_response,
        mock_settings_production
    ):
        """Test GitHub callback with invalid OAuth state."""
        mock_get_settings.return_value = mock_settings_production
        
        # Mock OAuth state repository to return None (invalid state)
        mock_oauth_repo = Mock(spec=OAuthStateRepository)
        mock_oauth_repo.get_state.return_value = None
        mock_oauth_repo_class.return_value = mock_oauth_repo
        
        # Create properly encoded state but with invalid CSRF token  
        encoded_state = encode_oauth_state("invalid_state", "http://localhost:5173/")
        
        with pytest.raises(HTTPException) as exc_info:
            await github_callback(
                code="test_code",
                state=encoded_state,
                response=mock_response,
                session=mock_session
            )
        
        assert exc_info.value.status_code == 400
        assert "Invalid or expired OAuth state" in str(exc_info.value.detail)
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository')
    @patch('tarsy.controllers.auth.now_us')
    async def test_github_callback_expired_oauth_state(
        self,
        mock_now_us,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_session,
        mock_response,
        mock_settings_production
    ):
        """Test GitHub callback with expired OAuth state."""
        mock_get_settings.return_value = mock_settings_production
        mock_now_us.return_value = 1609459800_000_000  # Later time
        
        # Mock expired OAuth state
        mock_oauth_state = Mock()
        mock_oauth_state.expires_at = 1609459200_000_000  # Earlier expiry
        
        mock_oauth_repo = Mock(spec=OAuthStateRepository)
        mock_oauth_repo.get_state.return_value = mock_oauth_state
        mock_oauth_repo_class.return_value = mock_oauth_repo
        
        # Create properly encoded state with expired CSRF token
        encoded_state = encode_oauth_state("expired_state", "http://localhost:5173/")
        
        with pytest.raises(HTTPException) as exc_info:
            await github_callback(
                code="test_code",
                state=encoded_state,
                response=mock_response,
                session=mock_session
            )
        
        assert exc_info.value.status_code == 400
        assert "Invalid or expired OAuth state" in str(exc_info.value.detail)


@pytest.mark.unit
class TestHybridAuthentication:
    """Test hybrid authentication with Bearer tokens and cookies."""
    
    async def test_verify_jwt_token_bearer_token_priority(self):
        """Test that Bearer token takes priority over cookie."""
        from fastapi import Request
        from fastapi.security import HTTPAuthorizationCredentials
        
        # Mock request with both Bearer token and cookie
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": "cookie_token"}
        
        # Mock Bearer token credentials
        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "bearer_token"
        
        # Mock JWT service
        mock_jwt_service = Mock()
        mock_jwt_service.verify_jwt_token.return_value = {
            "sub": "service_account:test",
            "service_account": True
        }
        
        result = await verify_jwt_token(mock_request, mock_credentials, mock_jwt_service)
        
        # Should use Bearer token, not cookie
        mock_jwt_service.verify_jwt_token.assert_called_once_with("bearer_token")
        assert result["service_account"] is True
    
    async def test_verify_jwt_token_cookie_fallback(self):
        """Test fallback to cookie when no Bearer token provided."""
        from fastapi import Request
        
        # Mock request with only cookie
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": "cookie_token"}
        
        # No Bearer token
        mock_credentials = None
        
        # Mock JWT service
        mock_jwt_service = Mock()
        mock_jwt_service.verify_jwt_token.return_value = {
            "sub": "user123",
            "username": "testuser"
        }
        
        result = await verify_jwt_token(mock_request, mock_credentials, mock_jwt_service)
        
        # Should use cookie token
        mock_jwt_service.verify_jwt_token.assert_called_once_with("cookie_token")
        assert result["username"] == "testuser"
    
    async def test_verify_jwt_token_no_authentication(self):
        """Test error when no authentication provided."""
        from fastapi import Request
        
        # Mock request with no cookie
        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        
        # No Bearer token
        mock_credentials = None
        
        # Mock JWT service (shouldn't be called)
        mock_jwt_service = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_request, mock_credentials, mock_jwt_service)
        
        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail
        mock_jwt_service.verify_jwt_token.assert_not_called()


@pytest.mark.unit  
class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    @patch('tarsy.controllers.auth.get_settings')
    async def test_logout_endpoint(self, mock_get_settings, mock_response, mock_settings_hybrid):
        """Test logout endpoint clears cookie."""
        mock_get_settings.return_value = mock_settings_hybrid
        
        result = await logout(mock_response)
        
        # Should clear the access_token cookie
        mock_response.delete_cookie.assert_called_once_with(
            key="access_token",
            path="/",
            samesite="strict",
            domain=None  # cookie_domain is None in mock settings
        )
        assert result == {"message": "Successfully logged out"}
    
    @patch('tarsy.controllers.auth.get_settings') 
    async def test_logout_with_cookie_domain(self, mock_get_settings, mock_response):
        """Test logout endpoint with cookie_domain setting."""
        settings = Mock()
        settings.cookie_domain = ".example.com"
        mock_get_settings.return_value = settings
        
        result = await logout(mock_response)
        
        # Should clear cookie with specified domain
        mock_response.delete_cookie.assert_called_once_with(
            key="access_token",
            path="/",
            samesite="strict",
            domain=".example.com"
        )
        assert result == {"message": "Successfully logged out"}
    
    @patch('tarsy.controllers.auth.JWTService')
    async def test_get_token_from_cookie_valid_cookie(self, mock_jwt_service_class):
        """Test WebSocket token helper with valid cookie."""
        from fastapi import Request
        
        # Mock request with valid cookie
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": "valid_cookie_token"}
        
        # Mock JWT service
        mock_jwt_service = Mock()
        mock_jwt_service_class.return_value = mock_jwt_service
        mock_jwt_service.verify_jwt_token.return_value = {
            "sub": "user123",
            "username": "testuser"
        }
        
        result = await get_token_from_cookie(mock_request)
        
        assert result == {"access_token": "valid_cookie_token"}
        mock_jwt_service.verify_jwt_token.assert_called_once_with("valid_cookie_token")
    
    async def test_get_token_from_cookie_no_cookie(self):
        """Test WebSocket token helper with no cookie."""
        from fastapi import Request
        
        # Mock request with no cookie
        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        
        with pytest.raises(HTTPException) as exc_info:
            await get_token_from_cookie(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "No authentication cookie found" in exc_info.value.detail
    
    @patch('tarsy.controllers.auth.JWTService')
    async def test_get_token_from_cookie_invalid_cookie(self, mock_jwt_service_class):
        """Test WebSocket token helper with invalid cookie."""
        from fastapi import Request
        
        # Mock request with invalid cookie
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": "invalid_cookie_token"}
        
        # Mock JWT service to raise exception
        mock_jwt_service = Mock()
        mock_jwt_service_class.return_value = mock_jwt_service
        mock_jwt_service.verify_jwt_token.side_effect = HTTPException(401, "Invalid token")
        
        with pytest.raises(HTTPException) as exc_info:
            await get_token_from_cookie(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "Authentication cookie is invalid or expired" in exc_info.value.detail


@pytest.mark.unit
class TestStateParameterEncoding:
    """Test OAuth state parameter encoding/decoding functionality."""
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository')
    @patch('tarsy.controllers.auth.uuid4')
    @patch('tarsy.controllers.auth.now_us')
    async def test_login_creates_encoded_state(
        self, 
        mock_now_us,
        mock_uuid4,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_settings_hybrid
    ):
        """Test that login endpoint creates properly encoded state."""
        mock_get_settings.return_value = mock_settings_hybrid
        mock_uuid4.return_value = "test_csrf_token"
        mock_now_us.return_value = 1609459200_000_000  # 2021-01-01 00:00:00 UTC
        
        # Mock OAuth state repository
        mock_oauth_repo = Mock()
        mock_oauth_repo_class.return_value = mock_oauth_repo
        mock_oauth_repo.create_state.return_value = True
        
        # Mock session
        mock_session = Mock()
        
        with patch('builtins.__import__') as mock_import:
            # Mock minimal authlib behavior
            def import_side_effect(name, *args, **kwargs):
                if name == 'authlib.integrations.httpx_client':
                    mock_module = Mock()
                    mock_client = Mock()
                    mock_client.return_value.create_authorization_url.return_value = (
                        "https://github.com/login/oauth/authorize?state=encoded_state",
                        "encoded_state"
                    )
                    mock_module.AsyncOAuth2Client = mock_client
                    return mock_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = await github_login(
                session=mock_session,
                redirect_url="http://localhost:5173/"
            )
            
            # Verify state was created with CSRF token
            mock_oauth_repo.create_state.assert_called_once()
            created_state_args = mock_oauth_repo.create_state.call_args[0]
            assert created_state_args[0] == "test_csrf_token"  # csrf_token
            
            assert isinstance(result, RedirectResponse)
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository') 
    @patch('tarsy.controllers.auth.JWTService')
    @patch('tarsy.controllers.auth.validate_github_membership')
    async def test_callback_decodes_state_parameter(
        self,
        mock_validate_membership,
        mock_jwt_service_class,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_response,
        mock_settings_hybrid
    ):
        """Test that callback endpoint decodes state parameter correctly."""
        mock_get_settings.return_value = mock_settings_hybrid
        
        # Mock GitHub membership validation to be async and pass
        async def mock_validate_async(*args, **kwargs):
            pass  # Validation passes
        mock_validate_membership.side_effect = mock_validate_async
        
        # Create encoded state
        encoded_state = encode_oauth_state("test_csrf", "http://localhost:5173/")
        
        # Mock OAuth state repository
        mock_oauth_repo = Mock()
        mock_oauth_repo_class.return_value = mock_oauth_repo
        mock_oauth_state = Mock()
        mock_oauth_state.expires_at = 9999999999_000_000  # Future timestamp
        mock_oauth_repo.get_state.return_value = mock_oauth_state
        mock_oauth_repo.delete_state.return_value = True
        
        # Mock JWT service
        mock_jwt_service = Mock()
        mock_jwt_service_class.return_value = mock_jwt_service
        mock_jwt_service.create_user_jwt_token.return_value = "test_jwt_token"
        
        # Mock session
        mock_session = Mock()
        
        with patch('tarsy.controllers.auth.now_us', return_value=1000000000_000_000):
            # Save the original import before patching
            original_import = __import__
            with patch('builtins.__import__') as mock_import:
                # Mock minimal authlib behavior
                def import_side_effect(name, *args, **kwargs):
                    if name == 'authlib.integrations.httpx_client':
                        mock_module = Mock()
                        mock_client = Mock()
                        mock_client_instance = Mock()
                        # Make fetch_token an async mock that returns a dictionary
                        async def mock_fetch_token(*args, **kwargs):
                            return {"access_token": "github_token"}
                        mock_client_instance.fetch_token = mock_fetch_token
                        mock_client.return_value = mock_client_instance
                        mock_module.AsyncOAuth2Client = mock_client
                        return mock_module
                    return original_import(name, *args, **kwargs)
                
                mock_import.side_effect = import_side_effect
                
                with patch('httpx.AsyncClient') as mock_http_client:
                    # Mock GitHub API response
                    mock_http_instance = Mock()
                    mock_http_client.return_value.__aenter__.return_value = mock_http_instance
                    mock_user_response = Mock()
                    mock_user_response.json.return_value = {
                        "id": 12345,
                        "login": "testuser",
                        "email": "test@example.com",
                        "avatar_url": "https://github.com/avatar.png"
                    }
                    mock_http_instance.get.return_value = mock_user_response
                    
                    result = await github_callback(
                        code="test_code",
                        state=encoded_state,
                        response=mock_response,
                        session=mock_session
                    )
                    
                    # Verify state was looked up with correct CSRF token
                    mock_oauth_repo.get_state.assert_called_once_with("test_csrf")
                    
                    # Verify redirect to the correct URL from decoded state
                    assert isinstance(result, RedirectResponse)
                    assert "http://localhost:5173/" in str(result.headers['location'])
    
    async def test_invalid_state_parameter_format(self, mock_response):
        """Test callback with malformed state parameter."""
        # Mock session
        mock_session = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await github_callback(
                code="test_code",
                state="invalid_base64_state",  # Not valid base64
                response=mock_response,
                session=mock_session
            )
        
        assert exc_info.value.status_code == 400
        assert "Invalid OAuth state parameter" in exc_info.value.detail


@pytest.mark.unit
class TestRedirectValidation:
    """Test redirect URL validation in login endpoint."""
    
    @patch('tarsy.controllers.auth.get_settings')
    async def test_dev_mode_localhost_validation(self, mock_get_settings):
        """Test that dev mode allows localhost URLs with any port."""
        settings = Mock()
        settings.dev_mode = True
        mock_get_settings.return_value = settings
        
        # Mock session
        mock_session = Mock()
        
        # Test valid localhost URLs
        valid_urls = [
            "http://localhost:3000/",
            "http://localhost:5173/",
            "https://localhost:8080/callback",
            "http://localhost:3000/some/path?param=value"
        ]
        
        for url in valid_urls:
            # Should not raise exception
            result = await github_login(session=mock_session, redirect_url=url)
            assert isinstance(result, RedirectResponse)
    
    @patch('tarsy.controllers.auth.get_settings')
    async def test_dev_mode_invalid_url_rejection(self, mock_get_settings):
        """Test that dev mode rejects non-localhost URLs."""
        settings = Mock()
        settings.dev_mode = True
        mock_get_settings.return_value = settings
        
        # Mock session
        mock_session = Mock()
        
        # Test invalid URLs
        invalid_urls = [
            "http://example.com:3000/",
            "https://malicious-site.com/",
            "http://127.0.0.1:3000/",  # IP address not allowed
            "ftp://localhost:21/"  # Wrong protocol
        ]
        
        for url in invalid_urls:
            with pytest.raises(HTTPException) as exc_info:
                await github_login(session=mock_session, redirect_url=url)
            
            assert exc_info.value.status_code == 400
            assert "Dev mode: redirect URL must be localhost" in exc_info.value.detail
    
    @patch('tarsy.controllers.auth.get_settings')
    async def test_production_mode_frontend_url_validation(self, mock_get_settings):
        """Test that production mode only allows frontend_url."""
        settings = Mock()
        settings.dev_mode = False
        settings.frontend_url = "https://app.example.com"
        settings.oauth_state_ttl_minutes = 10  # Add numeric value
        settings.github_client_id = "test_client_id"
        settings.github_client_secret = "test_client_secret"
        settings.github_callback_url = "https://api.example.com/auth/callback"
        mock_get_settings.return_value = settings
        
        # Mock session and OAuth dependencies
        mock_session = Mock()
        
        with patch('tarsy.controllers.auth.OAuthStateRepository') as mock_oauth_repo_class:
            with patch('tarsy.controllers.auth.uuid4', return_value="test_csrf"):
                with patch('tarsy.controllers.auth.now_us', return_value=1609459200_000_000):
                    mock_oauth_repo = Mock()
                    mock_oauth_repo_class.return_value = mock_oauth_repo
                    mock_oauth_repo.create_state.return_value = True
                    
                    with patch('builtins.__import__') as mock_import:
                        # Mock minimal authlib behavior
                        def import_side_effect(name, *args, **kwargs):
                            if name == 'authlib.integrations.httpx_client':
                                mock_module = Mock()
                                mock_client = Mock()
                                mock_client.return_value.create_authorization_url.return_value = ("https://github.com/oauth", "state")
                                mock_module.AsyncOAuth2Client = mock_client
                                return mock_module
                            return __import__(name, *args, **kwargs)
                        
                        mock_import.side_effect = import_side_effect
                        
                        # Valid URL (matches frontend_url prefix)
                        result = await github_login(
                            session=mock_session,
                            redirect_url="https://app.example.com/dashboard"
                        )
                        assert isinstance(result, RedirectResponse)
                        
                        # Invalid URL (doesn't match frontend_url)
                        with pytest.raises(HTTPException) as exc_info:
                            await github_login(
                                session=mock_session,
                                redirect_url="https://malicious-site.com/"
                            )
                        
                        assert exc_info.value.status_code == 400
                        assert "Production mode: redirect URL must start with https://app.example.com" in exc_info.value.detail
