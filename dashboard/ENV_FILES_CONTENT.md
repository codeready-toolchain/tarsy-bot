# Environment Files to Create

## 1. Create `dashboard/.env.local` (for your local development)
```bash
# Local Development Environment
# Copy from .env.example and customize for your local setup

# Backend API Configuration
VITE_API_BASE_URL=http://localhost:4180
VITE_WS_BASE_URL=ws://localhost:4180

# Frontend Development Server
VITE_DEV_SERVER_HOST=localhost
VITE_DEV_SERVER_PORT=5173

# OAuth2 Proxy Configuration
VITE_OAUTH_PROXY_URL=http://localhost:4180

# Environment
VITE_NODE_ENV=development
```

## 2. Create `dashboard/.env` (default fallbacks)
```bash
# Default Environment Configuration
# These are fallback values - override in .env.local

# Backend API Configuration
VITE_API_BASE_URL=http://localhost:4180
VITE_WS_BASE_URL=ws://localhost:4180

# Frontend Development Server
VITE_DEV_SERVER_HOST=localhost
VITE_DEV_SERVER_PORT=5173

# OAuth2 Proxy Configuration
VITE_OAUTH_PROXY_URL=http://localhost:4180
```

## Environment Loading Order
1. `.env.local` (highest priority - for personal overrides)
2. `.env.development` / `.env.production` (environment-specific)
3. `.env` (lowest priority - defaults)

## Production Environment
For production, set these environment variables in your deployment platform:
- `VITE_API_BASE_URL=https://your-backend-domain.com`
- `VITE_WS_BASE_URL=wss://your-backend-domain.com`
- `VITE_OAUTH_PROXY_URL=https://your-oauth-proxy-domain.com`
- `VITE_NODE_ENV=production`
