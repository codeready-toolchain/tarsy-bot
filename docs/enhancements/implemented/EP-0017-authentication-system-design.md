# EP-0017: Authentication System - Design Document

**Created:** 2025-01-01  

---

## Design Overview

### Architecture Summary

Transform the current unprotected API into a unified JWT-based authentication system. All endpoints (except health checks) validate JWT tokens issued after GitHub OAuth authentication with org/team membership validation. This eliminates the complexity of dual authentication mechanisms while maintaining security.

**Key Principles:**
- **Unified JWT Authentication**: Single token-based auth for all endpoints
- **Stateless Design**: No server-side sessions, all state in JWT tokens  
- **Security-First**: Follow OAuth 2.0 and JWT standards with RSA key signing
- **Configuration-Based**: All secrets and keys via environment variables
- **Developer-Friendly**: Service account tokens for automation and development

### Authentication Matrix

| Endpoint Category           | Authentication Method | Token Type           | Use Case                      |
|-----------------------------|-----------------------|----------------------|-------------------------------|
| `POST /alerts`              | Hybrid Auth*          | User or Service      | All alert submissions         |
| `GET /api/v1/history/*`     | Hybrid Auth*          | User or Service      | All API access                |
| `WebSocket /ws/dashboard/*` | Bearer JWT Token      | User or Service      | All WebSocket connections     |
| `GET /health`               | None                  | N/A                  | System monitoring             |

***Hybrid Authentication**: Supports both HTTP-only cookies (web users) and Bearer tokens (service accounts) on the same endpoints*

### Hybrid Authentication Design

**Phase 7** introduces a hybrid authentication approach with state-encoded redirects that supports both secure cookie-based authentication for web users and Bearer token authentication for service accounts:

**Web Users (OAuth Flow with State-Encoded Redirects)**:
1. Frontend specifies desired redirect URL via query parameter: `/auth/login?redirect_url=http://localhost:3001/`
2. Backend validates redirect URL (dev mode: any localhost port; production: only configured frontend URL)
3. Redirect URL is cryptographically encoded into OAuth state parameter for security
4. After successful authentication, user is redirected to their original requesting frontend
5. Authentication stored as secure HTTP-only cookies (immune to XSS attacks)
6. CSRF protection with `SameSite=Strict` cookies and OAuth state validation

**Service Accounts (Bearer Tokens)**:
1. Long-lived JWT tokens generated via Makefile for automation
2. Standard `Authorization: Bearer <token>` header authentication  
3. Same endpoints accessible via both authentication methods
4. Backward compatibility with existing service account integrations

**State Parameter Security**:
- Redirect URL encoded in OAuth state parameter using JSON + Base64
- State contains both CSRF token and redirect URL
- Only CSRF token stored in database (not full redirect URL)
- Prevents tampering with redirect destinations
- Built-in validation against allowed origins

**Benefits**:
- **Single Frontend Support**: Dashboard handles all authentication flows
- **Secure Redirects**: State-encoded redirects prevent open redirect vulnerabilities
- **Environment-Aware**: Dev mode allows any localhost port, production restricts to configured URL
- **Security First**: HTTP-only cookies prevent XSS token theft
- **Dual Support**: Single endpoints serve both users and service accounts
- **Industry Standard**: Follows OAuth 2.0 best practices for SPAs and state parameters
- **Developer Friendly**: Service accounts work unchanged
- **Simplified Frontend**: No JWT token management in browser JavaScript

---

## JWT Authentication System

### Token Types

**User JWT Tokens**: Issued after GitHub OAuth authentication with org/team validation
- **Expiration**: 1 week (configurable)
- **Claims**: `sub` (user_id), `username`, `email`, `avatar_url`, `exp`, `iat`
- **Issuer**: Backend service

**Service Account JWT Tokens**: Generated via Makefile for automation
- **Expiration**: None (long-lived tokens for service accounts)
- **Claims**: `sub` (service_account_name), `service_account: true`, `iat`
- **Issuer**: Backend service

**Token Format**: Standard JWT Bearer tokens
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Service Account Token Generation

**Makefile Target for Service Account Tokens:**
```bash
make generate-service-token SERVICE_NAME=monitoring
# Output: Generated service account JWT: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### JWT Configuration

**Environment Variables:**

*File: `.env` or environment variables*
```bash
# JWT Token Configuration
JWT_PRIVATE_KEY_PATH=/path/to/jwt-private-key.pem
JWT_PUBLIC_KEY_PATH=/path/to/jwt-public-key.pem
JWT_ALGORITHM=RS256
JWT_ISSUER=tarsy-backend
USER_TOKEN_EXPIRY_HOURS=168  # 1 week
```

**Key Generation (one-time setup):**

*Commands to run in project root*
```bash
# Generate RSA key pair for JWT signing
openssl genrsa -out jwt-private-key.pem 2048
openssl rsa -in jwt-private-key.pem -pubout -out jwt-public-key.pem
```

---

## GitHub OAuth Flow

### OAuth Flow Architecture

**Registration Requirements:**
- GitHub OAuth App registered with callback URL: `{BACKEND_URL}/auth/callback`
- Required scopes: `user:email`, `read:org` (for organization and optional team membership)
- Store credentials in environment variables

**Configuration:**

*File: `.env` or environment variables*
```bash
# GitHub OAuth Configuration
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret  
GITHUB_ORG=your-organization
GITHUB_TEAM=allowed-team-name  # Optional: if specified, team membership required
```

### Authentication Endpoints

**OAuth State Storage**: Temporary database storage for OAuth state parameter

*File: `backend/tarsy/models/db_models.py`*
```python
# Minimal OAuth state model for CSRF protection
class OAuthState(Base):
    """Temporary OAuth state storage for CSRF protection."""
    __tablename__ = "oauth_states"
    
    state: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 10 minutes TTL
```

**OAuth State Repository**: Repository pattern for database operations

*File: `backend/tarsy/repositories/oauth_state_repository.py`*
```python
from typing import Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from tarsy.models.db_models import OAuthState
from tarsy.utils.time import now_us

class OAuthStateRepository:
    """Repository for OAuth state database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_state(self, state: str, expires_at: int) -> OAuthState:
        """Create a new OAuth state."""
        oauth_state = OAuthState(
            state=state,
            created_at=now_us(),
            expires_at=expires_at
        )
        self.session.add(oauth_state)
        await self.session.commit()
        return oauth_state
    
    async def get_state(self, state: str) -> Optional[OAuthState]:
        """Get OAuth state by state parameter."""
        result = await self.session.execute(
            select(OAuthState).filter(OAuthState.state == state)
        )
        return result.scalar_one_or_none()
    
    async def delete_state(self, state: str) -> None:
        """Delete OAuth state."""
        await self.session.execute(
            delete(OAuthState).filter(OAuthState.state == state)
        )
        await self.session.commit()
    
    async def cleanup_expired_states(self) -> int:
        """Clean up expired OAuth states and return count of deleted records."""
        current_time = now_us()
        result = await self.session.execute(
            delete(OAuthState).where(OAuthState.expires_at < current_time)
        )
        await self.session.commit()
        return result.rowcount
```

**Database Initialization with Repository**:

*File: `backend/tarsy/database/__init__.py` or `backend/tarsy/database/init.py`*
```python
from sqlalchemy.ext.asyncio import AsyncSession
from tarsy.database.engine import engine
from tarsy.models.base import Base
from tarsy.repositories.oauth_state_repository import OAuthStateRepository
import logging

logger = logging.getLogger(__name__)

async def init_database():
    """Initialize database and clean up expired states."""
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Clean up expired OAuth states on startup using repository
    async with AsyncSession(engine) as session:
        oauth_repo = OAuthStateRepository(session)
        deleted_count = await oauth_repo.cleanup_expired_states()
        logger.info(f"Cleaned up {deleted_count} expired OAuth states")
```

**New Endpoints to Implement:**

*File: `backend/tarsy/controllers/auth.py`*
```python
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tarsy.database import get_session
from tarsy.repositories.oauth_state_repository import OAuthStateRepository
from tarsy.services.jwt_service import JWTService
from tarsy.services.github_service import validate_github_membership
from tarsy.config.settings import get_settings
from tarsy.utils.time import now_us
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

@router.get("/login")
async def github_login(session: AsyncSession = Depends(get_session)):
    """Start GitHub OAuth flow by redirecting to GitHub with state parameter."""
    settings = get_settings()
    
    # Generate and store OAuth state for CSRF protection using repository
    state = str(uuid4())
    expires_at = now_us() + 600_000_000  # 10 minutes in microseconds
    
    oauth_repo = OAuthStateRepository(session)
    await oauth_repo.create_state(state, expires_at)
    
    # Build GitHub OAuth URL
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.backend_url}/auth/callback"
        f"&scope=user:email,read:org"
        f"&state={state}"
    )
    
    return RedirectResponse(github_url)
    
@router.get("/callback") 
async def github_callback(
    code: str, 
    state: str, 
    session: AsyncSession = Depends(get_session)
):
    """Handle GitHub OAuth callback, validate membership, and return JWT token."""
    try:
        oauth_repo = OAuthStateRepository(session)
        
        # Validate OAuth state to prevent CSRF
        oauth_state = await oauth_repo.get_state(state)
        if not oauth_state or oauth_state.expires_at < now_us():
            raise HTTPException(400, "Invalid or expired OAuth state")
        
        # Clean up used state
        await oauth_repo.delete_state(state)
        
        # Exchange code for access token using authlib
        from authlib.integrations.httpx_client import AsyncOAuth2Client
        
        oauth_client = AsyncOAuth2Client(
            client_id=get_settings().github_client_id,
            client_secret=get_settings().github_client_secret
        )
        
        token_response = await oauth_client.fetch_token(
            token_url="https://github.com/login/oauth/access_token",
            code=code,
            redirect_uri=f"{get_settings().backend_url}/auth/callback"
        )
        
        github_access_token = token_response['access_token']
        
        # Get user data and validate membership
        from github import Github
        g = Github(github_access_token)
        github_user = g.get_user()
        
        # Validate org/team membership (raises HTTPException if invalid)
        await validate_github_membership(github_access_token, github_user.login)
        
        # Generate JWT token with user claims
        jwt_service = JWTService(get_settings())
        jwt_token = jwt_service.create_user_jwt_token(
            user_id=str(github_user.id),
            username=github_user.login,
            email=github_user.email,
            avatar_url=github_user.avatar_url
        )
        
        return {"jwt_token": jwt_token}
        
    except HTTPException:
        raise  # Re-raise validation errors (403, etc.)
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(500, "OAuth callback failed")
    
```

**Router Registration**: Add to main.py to register the auth controller

*File: `backend/tarsy/main.py`*
```python
# Add import
from tarsy.controllers.auth import router as auth_router

# Register router (add after existing include_router calls)
app.include_router(auth_router, tags=["authentication"])
```

### JWT Token Management

**Why JWT Tokens:**
JWT tokens provide stateless authentication with all necessary information encoded:
1. **Stateless Design**: No server-side storage, all user info in token
2. **Self-Contained**: Token contains user identity and expiration
3. **Membership Validation**: Membership validated once at token issuance
4. **Scalability**: No database lookups for authentication validation
5. **Security**: RSA-signed tokens prevent tampering

**JWT Implementation:**

*File: `backend/tarsy/services/jwt_service.py`*
```python
from jwt import encode, decode, InvalidTokenError
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from tarsy.config.settings import Settings

class JWTService:
    """JWT token generation and validation service."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.algorithm = settings.jwt_algorithm
        self.issuer = settings.jwt_issuer
        
        # Load RSA keys
        with open(settings.jwt_private_key_path, 'rb') as f:
            self.private_key = serialization.load_pem_private_key(
                f.read(), password=None
            )
            
        with open(settings.jwt_public_key_path, 'rb') as f:
            self.public_key = serialization.load_pem_public_key(f.read())
    
    def create_user_jwt_token(
        self, 
        user_id: str, 
        username: str, 
        email: str, 
        avatar_url: str
    ) -> str:
        """Create JWT token for authenticated user."""
        now = datetime.utcnow()
        exp = now + timedelta(hours=self.settings.user_token_expiry_hours)
        
        payload = {
            "sub": user_id,
            "username": username,
            "email": email,
            "avatar_url": avatar_url,
            "iss": self.issuer,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp())
        }
        
        return encode(payload, self.private_key, algorithm=self.algorithm)
    
    def create_service_account_jwt_token(self, service_name: str) -> str:
        """Create long-lived JWT token for service accounts."""
        now = datetime.utcnow()
        
        payload = {
            "sub": f"service_account:{service_name}",
            "service_account": True,
            "iss": self.issuer,
            "iat": int(now.timestamp())
            # No expiration for service accounts
        }
        
        return encode(payload, self.private_key, algorithm=self.algorithm)
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token."""
        try:
            payload = decode(
                token, 
                self.public_key, 
                algorithms=[self.algorithm],
                issuer=self.issuer
            )
            return payload
        except InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )
```

### Protected Endpoint Integration

**Universal JWT Authentication Dependency:**

*File: `backend/tarsy/auth/dependencies.py`*
```python
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from tarsy.services.jwt_service import JWTService
from tarsy.config.settings import get_settings

security = HTTPBearer()
jwt_service = JWTService(get_settings())

async def verify_jwt_token(
    token: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Verify JWT token for all protected endpoints."""
    try:
        payload = jwt_service.verify_jwt_token(token.credentials)
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed"
        )

async def verify_jwt_token_websocket(
    token: str = Query(..., description="JWT token for authentication")
) -> Optional[Dict[str, Any]]:
    """Verify JWT token for WebSocket endpoints - returns None if invalid."""
    try:
        return jwt_service.verify_jwt_token(token)
    except Exception:
        return None
```

**Usage Examples**: How to apply JWT verification to endpoints

*File: `backend/tarsy/main.py` (for alerts endpoint)*
```python
from tarsy.auth.dependencies import verify_jwt_token

@app.post("/alerts", dependencies=[Depends(verify_jwt_token)])
async def submit_alert(request: Request):
    # Existing implementation unchanged
```

*File: `backend/tarsy/controllers/history_controller.py` (for history endpoints)*
```python
from tarsy.auth.dependencies import verify_jwt_token

@router.get("/sessions", dependencies=[Depends(verify_jwt_token)])
async def list_sessions(...):
    # Existing implementation unchanged

@router.get("/history/conversations", dependencies=[Depends(verify_jwt_token)])
async def get_conversations(...):
    # Existing implementation unchanged
```

**WebSocket Authentication:**

*File: `backend/tarsy/main.py` (for WebSocket endpoints)*
```python
from tarsy.auth.dependencies import verify_jwt_token_websocket

@app.websocket("/ws/dashboard/{user_id}")
async def dashboard_websocket_endpoint(
    websocket: WebSocket, 
    user_id: str,
    jwt_payload: Optional[Dict[str, Any]] = Depends(verify_jwt_token_websocket)
):
    if not jwt_payload:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
        
    await websocket.accept()
    # Token is valid, proceed with existing WebSocket logic
    # User info available in jwt_payload: jwt_payload['sub'], jwt_payload['username'], etc.
```

---

## Architecture Components

### Settings Configuration

**Extended Settings Class:**

*File: `backend/tarsy/config/settings.py`*
```python
from pydantic import BaseSettings, Field
from typing import Optional

class Settings(BaseSettings):
    # Existing settings...
    
    # GitHub OAuth  
    github_client_id: str = Field(default="")
    github_client_secret: str = Field(default="")
    github_org: str = Field(default="", description="Required GitHub organization")
    github_team: Optional[str] = Field(default=None, description="Optional GitHub team - if specified, team membership required")
    
    # JWT Configuration
    jwt_private_key_path: str = Field(default="keys/jwt-private-key.pem")
    jwt_public_key_path: str = Field(default="keys/jwt-public-key.pem")
    jwt_algorithm: str = Field(default="RS256")
    jwt_issuer: str = Field(default="tarsy-backend")
    user_token_expiry_hours: int = Field(default=168, description="User token expiry in hours (default: 1 week)")
    
    # OAuth State Management
    oauth_state_ttl_minutes: int = Field(default=10, description="OAuth state TTL in minutes")
```

### Security Components

**PyGithub Integration Benefits:**
- **Clean API**: High-level methods like `org.has_in_members(user)` vs raw HTTP calls
- **Built-in Error Handling**: Proper GitHub API exception handling with meaningful error types
- **Type Safety**: IDE autocomplete and type checking for GitHub API objects
- **Robust Authentication**: Handles GitHub API authentication seamlessly
- **Rate Limit Handling**: Built-in rate limiting and retry logic
- **Comprehensive Coverage**: Access to all GitHub API features if needed later

**GitHub Membership Validation:**

*File: `backend/tarsy/services/github_service.py`*
```python
async def validate_github_membership(github_access_token: str, username: str) -> None:
    """Validate GitHub org/team membership using PyGithub. Raises HTTPException if validation fails."""
    from github import Github
    from github.GithubException import UnknownObjectException, GithubException
    from fastapi import HTTPException, status
    
    settings = get_settings()
    
    try:
        # Initialize GitHub client with access token
        g = Github(github_access_token)
        user = g.get_user(username)
        org = g.get_organization(settings.github_org)
        
        # Check organization membership (required)
        if not org.has_in_members(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User '{username}' is not a member of GitHub organization '{settings.github_org}'"
            )
        
        # Check team membership (if configured)
        if settings.github_team:
            try:
                team = org.get_team_by_slug(settings.github_team)
                if not team.has_in_members(user):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"User '{username}' is not a member of GitHub team '{settings.github_team}' in organization '{settings.github_org}'"
                    )
            except UnknownObjectException:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"GitHub team '{settings.github_team}' not found in organization '{settings.github_org}'"
                )
                
    except GithubException as e:
        if e.status == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub access token is invalid or expired"
            )
        elif e.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"GitHub organization '{settings.github_org}' not found or not accessible"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"GitHub API error: {e.data.get('message', 'Unknown error')}"
            )
```

**JWT Security Features:**
- RSA-256 signature prevents token tampering
- Configurable expiration for user tokens
- No expiration for service account tokens  
- Issuer validation prevents token reuse from other systems

---

## Integration Strategy

### Development and Service Authentication

**Service Account Tokens** (Recommended for automation)
- Generate long-lived JWT tokens for services/development
- Same authentication flow as user tokens
- Easy to generate and revoke via Makefile

**Unified Authentication Approach:**
```python
# All endpoints use same JWT verification
@app.post("/alerts")
async def submit_alert(
    request: Request,
    jwt_payload: dict = Depends(verify_jwt_token)
):
    # jwt_payload contains user info or service account info
    # No need to differentiate - both are valid JWT tokens
    # Process alert...
```

### Frontend Integration

**Dashboard Authentication Flow:**
1. User clicks "Login with GitHub" → redirect to `/auth/login`
2. GitHub redirects to `/auth/callback` → validate membership → return JWT token
3. Frontend receives JWT token → store in `localStorage` and decode for user info
4. All API/WebSocket requests include `Authorization: Bearer <jwt_token>`

**Frontend Integration Key Points:**

**Dashboard Updates** (`dashboard/`):
- **API Client**: Add JWT token to existing axios request interceptor
- **Context Pattern**: Add AuthContext alongside existing SessionContext  
- **WebSocket Service**: Include JWT token as query parameter in existing WebSocket URL
- **Error Handling**: Extend existing axios response interceptor to handle 401 redirects to login

*Dashboard already uses proper patterns (axios interceptors, environment variables) that align perfectly with JWT token integration.*

**JWT Token Claims Example:**
JWT tokens are self-contained and include all necessary user information. Frontend applications should decode the JWT token directly using a library like `jwt-decode`:

```javascript
import { jwtDecode } from 'jwt-decode'
const userInfo = jwtDecode(jwt_token)
// Contains: user_id (sub), username, email, avatar_url, expires_at (exp)
```

*Note: No server endpoint needed - all user info is extracted from JWT token claims client-side*

---

## Development & Testing Setup

### **Test Environment**

**Test Token Generator Utility**: On-demand JWT token creation for comprehensive testing

*File: `backend/tests/utils/auth_utils.py`*
```python
from tarsy.services.jwt_service import JWTService
from tarsy.config.settings import Settings
from pathlib import Path
import os

def get_test_jwt_service() -> JWTService:
    """Get JWT service configured with dev keys (reused for testing)."""
    test_settings = Settings()
    test_settings.jwt_private_key_path = "keys/INSECURE-dev-jwt-private-key.pem"
    test_settings.jwt_public_key_path = "keys/INSECURE-dev-jwt-public-key.pem"
    test_settings.jwt_algorithm = "RS256"
    test_settings.jwt_issuer = "tarsy-test"
    return JWTService(test_settings)

def create_test_user_token(
    user_id: str = "test_user_123",
    username: str = "test-user", 
    email: str = "test@example.com",
    expired: bool = False
) -> str:
    """Generate test JWT token with custom claims."""
    jwt_service = get_test_jwt_service()
    
    if expired:
        # Create token that expired 1 hour ago for testing
        import jwt
        from datetime import datetime, timedelta
        payload = {
            "sub": user_id,
            "username": username, 
            "email": email,
            "iss": "tarsy-test",
            "iat": int((datetime.utcnow() - timedelta(hours=2)).timestamp()),
            "exp": int((datetime.utcnow() - timedelta(hours=1)).timestamp())
        }
        return jwt.encode(payload, jwt_service.private_key, algorithm="RS256")
    
    return jwt_service.create_user_jwt_token(user_id, username, email, "https://github.com/test.png")

# Test fixtures
VALID_TEST_TOKEN = create_test_user_token()
EXPIRED_TEST_TOKEN = create_test_user_token(expired=True)
ADMIN_TEST_TOKEN = create_test_user_token("admin_123", "test-admin", "admin@example.com")
```

**Test Key Files** (reuses dev keys for simplicity):
- `keys/INSECURE-dev-jwt-private-key.pem` (shared with dev environment)
- `keys/INSECURE-dev-jwt-public-key.pem` (shared with dev environment)

### **Development Environment**

**Dev Mode Configuration**: Simplified local development without GitHub OAuth setup

*File: `backend/tarsy/config/settings.py` (add to existing Settings class)*
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Development Mode
    dev_mode: bool = Field(default=False, description="Enable development mode (bypasses GitHub OAuth)")
    
    @property 
    def is_dev_keys(self) -> bool:
        """Check if using insecure development keys."""
        return "INSECURE" in self.jwt_private_key_path
        
    def validate_production_safety(self):
        """Ensure dev settings are not used in production."""
        if self.environment == "production":
            if self.dev_mode:
                raise RuntimeError("DEV_MODE cannot be enabled in production!")
            if self.is_dev_keys:
                raise RuntimeError("INSECURE dev keys cannot be used in production!")
```

**Dev Authentication Flow**: Bypass GitHub OAuth with hardcoded dev user

*File: `backend/tarsy/controllers/auth.py` (modify existing auth controller)*
```python
# Add to existing auth controller

# Hardcoded dev user (simple, no overrides)
DEV_USER = {
    "id": 999999,
    "login": "tarsy-dev-user", 
    "email": "dev@tarsy-local.invalid",
    "avatar_url": "https://github.com/github.png"
}

@router.get("/login")
async def github_login(session: AsyncSession = Depends(get_session)):
    """Start GitHub OAuth flow or dev mode login."""
    settings = get_settings()
    
    if settings.dev_mode:
        # Dev mode: Skip GitHub, redirect directly to callback with fake params
        logger.warning("🚨 DEV MODE: Using insecure development authentication! 🚨")
        return RedirectResponse(f"/auth/callback?code=dev_fake_code&state=dev_fake_state")
    
    # ... existing production OAuth flow ...

@router.get("/callback") 
async def github_callback(
    code: str, 
    state: str, 
    session: AsyncSession = Depends(get_session)
):
    """Handle GitHub OAuth callback or dev mode callback."""
    settings = get_settings()
    
    if settings.dev_mode:
        # Dev mode: Use hardcoded user data, generate real JWT
        logger.warning("🚨 DEV MODE: Generating JWT with fake user data! 🚨")
        
        jwt_service = JWTService(settings)
        jwt_token = jwt_service.create_user_jwt_token(
            user_id=str(DEV_USER["id"]),
            username=DEV_USER["login"],
            email=DEV_USER["email"], 
            avatar_url=DEV_USER["avatar_url"]
        )
        
        return {"jwt_token": jwt_token}
    
    # ... existing production OAuth flow ...
```

**Shared Key Files** (committed to repo, used for both dev and test):
- `keys/INSECURE-dev-jwt-private-key.pem`
- `keys/INSECURE-dev-jwt-public-key.pem`

**Makefile Integration**:

*File: `backend/Makefile` (modify existing dev target)*
```makefile
.PHONY: dev
dev: check-venv ## Start development server with auto-reload
	@echo "$(GREEN)Starting development server...$(NC)"
	@echo "$(YELLOW)🔓 DEV MODE: Authentication bypassed - DEV USER will be used$(NC)"
	@echo "$(YELLOW)⚠️  Using INSECURE committed dev keys!$(NC)"
	DEV_MODE=true JWT_PRIVATE_KEY_PATH=keys/INSECURE-dev-jwt-private-key.pem JWT_PUBLIC_KEY_PATH=keys/INSECURE-dev-jwt-public-key.pem .venv/bin/uvicorn tarsy.main:app --reload --port 8000 --log-level info

.PHONY: dev-prod-auth  
dev-prod-auth: check-venv ## Start development server with production authentication
	@echo "$(GREEN)Starting development server with PRODUCTION authentication...$(NC)"
	@echo "$(RED)🔐 GitHub OAuth required - configure .env with GitHub credentials$(NC)"
	.venv/bin/uvicorn tarsy.main:app --reload --port 8000 --log-level info
```

**Development Workflow**:
```bash
# Start all services (backend + dashboard frontend) - backend uses dev auth mode automatically
make dev

# Or start just backend in dev mode  
cd backend && make dev

# Start backend with production authentication (requires GitHub OAuth setup)
cd backend && make dev-prod-auth
```

**How Root Make Dev Works**:
- Root `make dev` calls `cd backend && make dev` for backend
- Since backend `make dev` uses dev auth mode, entire stack runs with dev auth
- Dashboard frontend gets dev auth automatically through backend API

**Safety Warnings**: Clear indicators when using insecure dev/test keys
- Console warnings with 🚨 emojis
- "INSECURE" prefix on shared key files
- Runtime validation prevents prod usage
- Obvious fake user data (`.invalid` email domain)
- Single key pair shared between dev and test environments

---

## Implementation Phases

### **Phase 1: Dependencies and Setup**

**1.1 Python Packages**
- Add to `backend/pyproject.toml`:
  - `authlib = "^1.3.0"`
  - `PyGithub = "^2.1.1"`  
  - `PyJWT = "^2.8.0"`
  - `cryptography = "^41.0.0"`

**1.2 Generate Dev Keys**
- Create `keys/INSECURE-dev-jwt-private-key.pem`
- Create `keys/INSECURE-dev-jwt-public-key.pem`

### **Phase 2: Core Infrastructure**

**2.1 Settings Configuration**
- Add JWT and GitHub OAuth fields to `backend/tarsy/config/settings.py`
- Add dev_mode field and validation methods
- Update existing Settings class

**2.2 Database Models**
- Add `OAuthState` model to `backend/tarsy/models/db_models.py`
- Include state, created_at, expires_at fields

**2.3 JWT Service**
- Create `backend/tarsy/services/jwt_service.py`
- Implement `JWTService` class with RSA key loading
- Add user and service account token generation methods
- Add token verification method

**2.4 GitHub Service**
- Create `backend/tarsy/services/github_service.py`
- Implement `validate_github_membership` function using PyGithub
- Handle GitHub API authentication and membership validation
- Include proper error handling for GitHub API exceptions

**2.5 Repository**
- Create `backend/tarsy/repositories/oauth_state_repository.py`
- Implement CRUD operations for OAuth states
- Add cleanup method for expired states

### **Phase 3: Database Integration**

**3.1 Database Initialization**
- Update `backend/tarsy/database/__init__.py` or create `init.py`
- Add OAuth state cleanup on startup
- Ensure `OAuthState` model is included in Base metadata

**3.2 Model Registration**
- Import `OAuthState` model in `backend/tarsy/database/init_db.py` for auto-creation
- Table will be created automatically via `SQLModel.metadata.create_all()`

### **Phase 4: Authentication Endpoints**

**4.1 Auth Controller**
- Create `backend/tarsy/controllers/auth.py`
- Implement `/auth/login` endpoint (production + dev mode)
- Implement `/auth/callback` endpoint (production + dev mode)
- Add hardcoded DEV_USER constant

*Note: No `/auth/user` endpoint needed - JWT tokens are self-contained. Frontend applications should decode JWT tokens directly using `jwt-decode` or similar libraries.*

**4.2 Router Registration**
- Update `backend/tarsy/main.py` to import and register auth router
- Add auth router to existing `app.include_router()` calls

### **Phase 5: Authentication Middleware**

**5.1 JWT Dependencies**
- Create `backend/tarsy/auth/dependencies.py`
- Implement `verify_jwt_token` function for HTTP endpoints
- Implement `verify_jwt_token_websocket` function for WebSocket endpoints

**5.2 Protect Existing Endpoints**
- **Main.py endpoints** - Add JWT dependency to:
  - `POST /alerts` (alert submission)
  - `GET /alert-types` (dev UI support)
  - `GET /session-id/{alert_id}` (session lookup)
  - `WebSocket /ws/dashboard/{user_id}` (dashboard WebSocket)
- **History controller endpoints** - Add JWT dependency to:
  - `GET /api/v1/history/sessions` (list sessions)
  - `GET /api/v1/history/sessions/{session_id}` (session details)
  - `GET /api/v1/history/sessions/{session_id}/summary` (session summary)
  - `GET /api/v1/history/active-sessions` (active sessions)
  - `GET /api/v1/history/filter-options` (filter options)
- **Unprotected endpoints** (no JWT required):
  - `GET /` (root health check)
  - `GET /health` (main service health check)
  - `GET /api/v1/history/health` (history service health check)

### **Phase 6: Testing and Development**

**6.1 Test Utilities**
- Create `backend/tests/utils/auth_utils.py`
- Implement test token generation functions
- Create test fixtures (VALID_TEST_TOKEN, EXPIRED_TEST_TOKEN, etc.)

**6.2 Makefile Integration**
- Modify existing `backend/Makefile` `dev` target to support auth dev mode
- Add `generate-jwt-keys` target for production RSA key generation
- Add `generate-service-token` target for service account JWT creation

### **Phase 7: Hybrid Authentication Implementation**

**7.1 OAuth Login Enhancement**

*File: `backend/tarsy/controllers/auth.py` (modify existing login endpoint)*
```python
from fastapi import Query
import json
import base64
import re

@router.get("/login")
async def github_login(
    session: AsyncSession = Depends(get_session),
    redirect_url: str = Query(default="http://localhost:5173/", description="URL to redirect after successful authentication")
):
    """Start GitHub OAuth flow with state-encoded redirect support."""
    settings = get_settings()
    
    # Validate redirect URL based on environment
    if settings.dev_mode:
        # Dev mode: allow any localhost port
        if not re.match(r'^https?://localhost:\d+/?.*', redirect_url):
            raise HTTPException(400, "Dev mode: redirect URL must be localhost")
    else:
        # Production: only allow configured frontend URL
        if not redirect_url.startswith(settings.frontend_url):
            raise HTTPException(400, f"Production mode: redirect URL must start with {settings.frontend_url}")
    
    if settings.dev_mode:
        # Dev mode: Skip GitHub, redirect directly to callback with encoded state
        logger.warning("🚨 DEV MODE: Using insecure development authentication! 🚨")
        
        # Encode redirect URL into state for dev callback
        state_data = {
            "csrf_token": "dev_fake_state",
            "redirect_url": redirect_url
        }
        encoded_state = base64.urlsafe_b64encode(
            json.dumps(state_data).encode()
        ).decode()
        
        return RedirectResponse(f"/auth/callback?code=dev_fake_code&state={encoded_state}")
    
    # Production OAuth flow
    # Generate and store OAuth state for CSRF protection
    csrf_token = str(uuid4())
    expires_at = now_us() + 600_000_000  # 10 minutes in microseconds
    
    # Encode redirect URL into OAuth state parameter
    state_data = {
        "csrf_token": csrf_token,
        "redirect_url": redirect_url
    }
    encoded_state = base64.urlsafe_b64encode(
        json.dumps(state_data).encode()
    ).decode()
    
    # Store only CSRF token in database (not full state data)
    oauth_repo = OAuthStateRepository(session)
    await oauth_repo.create_state(csrf_token, expires_at)
    
    # Build GitHub OAuth URL with encoded state
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.backend_url}/auth/callback"
        f"&scope=user:email,read:org"
        f"&state={encoded_state}"
    )
    
    return RedirectResponse(github_url)
```

**7.2 OAuth Callback Enhancement**

*File: `backend/tarsy/controllers/auth.py` (modify existing callback endpoint)*
```python
from fastapi import Response
import json
import base64

@router.get("/callback") 
async def github_callback(
    code: str, 
    state: str,
    response: Response,
    session: AsyncSession = Depends(get_session)
):
    """Handle GitHub OAuth callback with state-encoded redirect support."""
    settings = get_settings()
    
    # Decode state parameter to extract redirect URL and CSRF token
    try:
        state_data = json.loads(
            base64.urlsafe_b64decode(state.encode()).decode()
        )
        csrf_token = state_data["csrf_token"]
        redirect_url = state_data["redirect_url"]
    except Exception:
        raise HTTPException(400, "Invalid OAuth state parameter")
    
    if settings.dev_mode:
        # Dev mode: Use hardcoded user data, generate real JWT
        logger.warning("🚨 DEV MODE: Generating JWT with fake user data! 🚨")
        
        jwt_service = JWTService(settings)
        jwt_token = jwt_service.create_user_jwt_token(
            user_id=str(DEV_USER["id"]),
            username=DEV_USER["login"],
            email=DEV_USER["email"], 
            avatar_url=DEV_USER["avatar_url"]
        )
        
        # Set HTTP-only cookie for browser-based authentication
        _set_auth_cookie(response, jwt_token)
        
        # Redirect to original requesting frontend
        return RedirectResponse(redirect_url)
    
    # Production OAuth flow
    try:
        oauth_repo = OAuthStateRepository(session)
        
        # Validate OAuth CSRF token exists in database
        oauth_state = await oauth_repo.get_state(csrf_token)
        if not oauth_state or oauth_state.expires_at < now_us():
            raise HTTPException(400, "Invalid or expired OAuth state")
        
        # Clean up used state
        await oauth_repo.delete_state(csrf_token)
        
        # Exchange code for access token using authlib
        from authlib.integrations.httpx_client import AsyncOAuth2Client
        
        oauth_client = AsyncOAuth2Client(
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret
        )
        
        token_response = await oauth_client.fetch_token(
            token_url="https://github.com/login/oauth/access_token",
            code=code,
            redirect_uri=f"{settings.backend_url}/auth/callback"
        )
        
        github_access_token = token_response['access_token']
        
        # Get user data and validate membership
        from github import Github
        g = Github(github_access_token)
        github_user = g.get_user()
        
        # Validate org/team membership (raises HTTPException if invalid)
        await validate_github_membership(github_access_token, github_user.login)
        
        # Generate JWT token with user claims
        jwt_service = JWTService(settings)
        jwt_token = jwt_service.create_user_jwt_token(
            user_id=str(github_user.id),
            username=github_user.login,
            email=github_user.email or "",
            avatar_url=github_user.avatar_url or ""
        )
        
        # Set HTTP-only cookie for browser-based authentication
        _set_auth_cookie(response, jwt_token)
        
        # Redirect to original requesting frontend
        return RedirectResponse(redirect_url)
        
    except HTTPException:
        raise  # Re-raise validation errors (403, etc.)
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(500, "OAuth callback failed")

def _set_auth_cookie(response: Response, jwt_token: str) -> None:
    """Set secure HTTP-only authentication cookie."""
    settings = get_settings()
    
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,  # Prevents JavaScript access (XSS protection)
        secure=not settings.dev_mode,  # HTTPS only in production
        samesite="strict",  # CSRF protection
        max_age=7 * 24 * 60 * 60,  # 7 days (matches JWT expiry)
        path="/",  # Available to all paths
        domain=settings.cookie_domain  # Cross-subdomain support if configured
    )
```

**7.3 Logout Endpoint**

*File: `backend/tarsy/controllers/auth.py` (add new endpoint)*
```python
@router.post("/logout")
async def logout(response: Response):
    """Clear authentication cookie and log out user."""
    settings = get_settings()
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="strict",
        domain=settings.cookie_domain  # Must match domain used when setting cookie
    )
    return {"message": "Successfully logged out"}
```

**7.4 Hybrid Authentication Dependencies**

*File: `backend/tarsy/auth/dependencies.py` (modify existing dependencies)*
```python
from fastapi import Request

async def verify_jwt_token(
    request: Request,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Hybrid JWT verification supporting both Bearer tokens and cookies.
    
    Priority Order:
    1. Authorization: Bearer <token> (for service accounts and API clients)
    2. access_token cookie (for browser-based user authentication)
    
    This enables the same endpoints to serve both:
    - Service accounts using Bearer tokens
    - Web users using secure HTTP-only cookies
    """
    jwt_service = JWTService(get_settings())
    
    # Try Bearer token first (service accounts, API clients)
    if token:
        try:
            payload = jwt_service.verify_jwt_token(token.credentials)
            return payload
        except HTTPException:
            # If Bearer token is present but invalid, don't fall back to cookie
            raise
    
    # Fall back to cookie authentication (web users)
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        try:
            payload = jwt_service.verify_jwt_token(cookie_token)
            return payload
        except HTTPException as e:
            # Clear invalid cookie and require re-authentication
            logger.warning(f"Invalid authentication cookie, clearing: {e.detail}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication cookie expired or invalid"
            )
    
    # No valid authentication found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide Bearer token or valid session cookie"
    )

async def verify_jwt_token_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token for WebSocket authentication")
) -> Optional[Dict[str, Any]]:
    """
    WebSocket JWT verification.
    
    Note: WebSockets cannot use HTTP-only cookies, so they must use token query parameter.
    Frontend should extract token from cookie using server-side helper endpoint if needed.
    """
    try:
        jwt_service = JWTService(get_settings())
        return jwt_service.verify_jwt_token(token)
    except Exception as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        return None
```

**7.5 Settings Configuration**

*File: `backend/tarsy/config/settings.py` (add new fields)*
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Frontend URL for OAuth redirects (production mode)
    frontend_url: str = Field(default="http://localhost:5173", description="Production frontend URL for OAuth redirects")
    
    # Cookie configuration
    # Setting cookie_domain=".example.com" makes cookies available to all subdomains of example.com. 
    # Only use this when you control all subdomains and need cross-subdomain authentication.
    cookie_domain: Optional[str] = Field(default=None, description="Cookie domain for cross-subdomain sharing (e.g., '.example.com' for app.example.com + api.example.com)")
```

**7.6 WebSocket Token Helper Endpoint** (Optional)

*File: `backend/tarsy/controllers/auth.py` (add helper endpoint)*
```python
@router.get("/token")
async def get_token_from_cookie(request: Request):
    """
    Extract JWT token from HTTP-only cookie for WebSocket connections.
    
    Frontend can call this endpoint to get the token for WebSocket authentication
    since WebSockets cannot access HTTP-only cookies directly.
    """
    cookie_token = request.cookies.get("access_token")
    if not cookie_token:
        raise HTTPException(401, "No authentication cookie found")
    
    # Verify token is valid before returning
    jwt_service = JWTService(get_settings())
    try:
        payload = jwt_service.verify_jwt_token(cookie_token)
        return {"access_token": cookie_token}
    except HTTPException:
        raise HTTPException(401, "Authentication cookie is invalid or expired")
```

**7.7 Frontend Usage Examples**

**Dashboard Login Integration** (`dashboard/src/components/auth/LoginPage.tsx`):
```javascript
const handleLogin = () => {
    // Redirect to login with dashboard-specific URL
    const redirectUrl = "http://localhost:5173/dashboard";
    window.location.href = `/auth/login?redirect_url=${encodeURIComponent(redirectUrl)}`;
};
```

**Production Example**:
```javascript
const handleLogin = () => {
    // Production frontend with custom redirect path
    const redirectUrl = "https://yourdomain.com/app/dashboard";
    window.location.href = `/auth/login?redirect_url=${encodeURIComponent(redirectUrl)}`;
};
```

### **Phase 8: Front-end**

**8.1 Front-end Implementation**

### **Validation Steps**
- After Phase 1: Dependencies installed and dev keys generated
- After Phase 2: JWT service can generate and verify tokens
- After Phase 3: Database models and OAuth state management works
- After Phase 4: Auth endpoints return JWT tokens in both prod and dev mode
- After Phase 5: Protected endpoints require valid JWT tokens
- After Phase 6: Development workflow with `make dev` works and tests pass
- After Phase 7: State-encoded redirects support multi-frontend authentication with secure cookie storage
- After Phase 8: Frontend authentication integrated with cookie-based flow

---

## Security Considerations

### JWT Token Security
- Use RSA-256 signatures to prevent token tampering
- Cryptographically secure random key generation for RSA keys
- Store private keys securely with proper file permissions
- Configurable token expiration for user tokens

### OAuth Security  
- Validate OAuth state parameter to prevent CSRF attacks
- Use secure random state generation (`uuid4`)
- Implement state expiration and cleanup (10 minutes TTL)
- Validate GitHub organization/team membership at token issuance

### Hybrid Authentication Security (Phase 7)
- **State-Encoded Redirects**: Redirect URLs cryptographically protected in OAuth state parameter
- **Environment-Based URL Validation**: Dev mode allows localhost:*, production allows only configured frontend URL
- **CSRF Protection**: OAuth state validation prevents cross-site request forgery
- **No Open Redirects**: Strict URL validation prevents malicious redirect attacks
- **HTTP-only Cookies**: Prevent XSS-based token theft for web users
- **SameSite=Strict Cookies**: Provide additional CSRF protection
- **Bearer Token Fallback**: Maintains service account compatibility
- **Cookie Security Flags**: `Secure`, `HttpOnly` enforced in production
- **Token Validation Precedence**: Bearer > Cookie prevents authentication confusion

### General Security
- Implement proper error handling (don't leak authentication details)
- Use HTTPS in production for all authentication flows
- No server-side token storage reduces attack surface
- Regular cleanup of expired OAuth states from database

---

## Implementation Dependencies

### Python Packages
```python
# Add to pyproject.toml
authlib = "^1.3.0"          # OAuth client implementation
PyGithub = "^2.1.1"         # GitHub API wrapper for clean membership validation
PyJWT = "^2.8.0"            # JWT token generation and validation
cryptography = "^41.0.0"    # RSA key handling for JWT signatures
sqlalchemy = "^2.0.0"       # Database ORM for OAuth state storage
```

### Configuration Files
- `.env` updates - GitHub OAuth credentials and JWT key paths
- RSA key pair generation for JWT signing
- CORS configuration updates for auth endpoints

### Makefile Targets

*File: `Makefile` (add to existing Makefile)*
```makefile
# Generate RSA key pair for JWT signing (one-time setup)
generate-jwt-keys:
	@mkdir -p keys
	@openssl genrsa -out keys/jwt-private-key.pem 2048
	@openssl rsa -in keys/jwt-private-key.pem -pubout -out keys/jwt-public-key.pem
	@echo "JWT keys generated in keys/ directory"

# Generate service account JWT token
generate-service-token:
	@python -c "from tarsy.auth.jwt_service import JWTService; from tarsy.config.settings import get_settings; jwt = JWTService(get_settings()); print('Service account JWT token:'); print(jwt.create_service_account_jwt_token('$(SERVICE_NAME)'))"
```
