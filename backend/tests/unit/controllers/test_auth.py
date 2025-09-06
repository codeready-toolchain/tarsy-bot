"""
Unit tests for authentication controllers.

Focuses on core authentication flows. Complex OAuth edge cases and external
library mocking scenarios have been simplified to focus on business logic.
"""

from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from tarsy.controllers.auth import github_login, github_callback
from tarsy.repositories.oauth_state_repository import OAuthStateRepository


@pytest.fixture
def mock_session():
    """Mock database session."""
    return Mock()


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
        
        result = await github_login(mock_session)
        
        assert isinstance(result, RedirectResponse)
        assert "/auth/callback?code=dev_fake_code&state=dev_fake_state" in str(result.headers['location'])
    
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
            
            result = await github_login(mock_session)
            
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
            await github_login(mock_session)


@pytest.mark.unit
class TestGithubCallbackEndpoint:
    """Test GitHub OAuth callback endpoint."""
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.JWTService')
    async def test_github_callback_dev_mode(
        self,
        mock_jwt_service_class,
        mock_get_settings,
        mock_session,
        mock_settings_dev
    ):
        """Test GitHub callback in development mode."""
        mock_get_settings.return_value = mock_settings_dev
        
        # Mock JWT service
        mock_jwt_service = Mock()
        mock_jwt_service_class.return_value = mock_jwt_service
        mock_jwt_service.create_user_jwt_token.return_value = "dev_jwt_token"
        
        result = await github_callback(
            code="dev_fake_code",
            state="dev_fake_state", 
            session=mock_session
        )
        
        # Verify JWT token was created with actual dev user
        mock_jwt_service.create_user_jwt_token.assert_called_once_with(
            user_id="999999",
            username="tarsy-dev-user",
            email="dev@tarsy-local.invalid",
            avatar_url="https://github.com/github.png"
        )
        
        # Dev mode returns a dict, not a redirect
        assert result == {"jwt_token": "dev_jwt_token"}
    
    @patch('tarsy.controllers.auth.get_settings')
    @patch('tarsy.controllers.auth.OAuthStateRepository')
    async def test_github_callback_invalid_oauth_state(
        self,
        mock_oauth_repo_class,
        mock_get_settings,
        mock_session,
        mock_settings_production
    ):
        """Test GitHub callback with invalid OAuth state."""
        mock_get_settings.return_value = mock_settings_production
        
        # Mock OAuth state repository to return None (invalid state)
        mock_oauth_repo = Mock(spec=OAuthStateRepository)
        mock_oauth_repo.get_state.return_value = None
        mock_oauth_repo_class.return_value = mock_oauth_repo
        
        with pytest.raises(HTTPException) as exc_info:
            await github_callback(
                code="test_code",
                state="invalid_state",
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
        
        with pytest.raises(HTTPException) as exc_info:
            await github_callback(
                code="test_code",
                state="expired_state",
                session=mock_session
            )
        
        assert exc_info.value.status_code == 400
        assert "Invalid or expired OAuth state" in str(exc_info.value.detail)
