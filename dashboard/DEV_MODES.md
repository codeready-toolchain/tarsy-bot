# Development Modes

This dashboard supports two development modes to accommodate different authentication setups.

## Environment Files

### `.env.development` (Default Mode)
- Direct connection to backend on `localhost:8000`
- No authentication proxy
- Used by: `make dev`, `npm run dev`
- **Safe to commit** - contains no secrets

### `.env.auth` (Auth Mode) 
- Connection through oauth2-proxy on `localhost:4180`
- Real authentication via OAuth2 proxy
- Used by: `make dev-auth`, `npm run dev:auth`
- **Safe to commit** - contains no secrets

### `.env.local` (Personal Overrides)
- Optional file for personal development overrides
- Takes highest priority over other env files
- **Ignored by git** (safe for personal settings)

### `.env.example` (Template)
- Template showing available configuration options
- **Safe to commit** - documentation purposes

## Usage

### Default Development (Direct Backend)
```bash
# Root project
make dev

# Dashboard only
make dashboard
cd dashboard && npm run dev
```

### Auth Development (OAuth2 Proxy)
```bash
# Root project 
make dev-auth

# Dashboard only
make dashboard-auth  
cd dashboard && npm run dev:auth
```

## Prerequisites for Auth Mode

For auth mode to work, you need [OAuth2-Proxy](https://github.com/oauth2-proxy/oauth2-proxy) running on `localhost:4180`. The auth proxy should be configured to forward requests to your backend on `localhost:8000`.

**📖 For detailed oauth2-proxy setup instructions, see: [docs/oauth2-proxy-setup.md](../docs/oauth2-proxy-setup.md)**

## Environment Loading Priority

Vite loads environment variables in this order (highest to lowest priority):
1. `.env.local` (personal overrides, ignored by git)
2. `.env.[mode]` (`.env.auth` for auth mode, `.env.development` for development mode)
3. `.env` (not used - ignored by git for security)

## Configuration

All environment variables starting with `VITE_` are available in the frontend application. The main variables are:

- `VITE_API_BASE_URL` - Backend API URL
- `VITE_WS_BASE_URL` - WebSocket URL  
- `VITE_DEV_SERVER_HOST` - Frontend dev server host
- `VITE_DEV_SERVER_PORT` - Frontend dev server port
- `VITE_OAUTH_PROXY_URL` - OAuth2 proxy URL

## Git Safety

- `.env.development` and `.env.auth` are safe to commit (no secrets)
- `.env.local` is ignored by git (for personal settings)
- `.env` is ignored by git (for security - avoid using)
