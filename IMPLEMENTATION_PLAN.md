# TARSy Container & Dev Environment Cleanup Plan

## Phase 1: Clean Dev Environment

### 1.1 Remove OAuth2-proxy from Dev
- Delete `make dev-auth` target from Makefile
- Delete `make dev-auth-full` target from Makefile
- Remove `.env.auth` references
- Remove `dashboard/DEV_MODES.md` auth mode references

### 1.2 Simplify Dev Environment  
- `make dev` → frontend (`vite dev`) + backend (`uvicorn`) only
- No containers, no oauth2-proxy
- Direct API calls: frontend:3000 → backend:8000
- Remove CORS proxy complexity from dev

### 1.3 Update Configuration Files
- `dashboard/vite.config.ts`: remove oauth2-proxy targets for dev
- `dashboard/src/config/env.ts`: simplify dev vs container logic
- Backend CORS: add `localhost:3000` for dev mode

## Phase 2: Container Setup with Nginx

### 2.1 Create Production Frontend Build ✅ COMPLETED
- ✅ Replace `dashboard/Dockerfile` with multi-stage production build
- ✅ Stage 1: Build React app with `npm run build`
- ✅ Stage 2: Serve static files with nginx:alpine
- ✅ Create `dashboard/nginx.conf` for React Router support

### 2.2 Create Nginx Reverse Proxy ✅ COMPLETED
- ✅ Create `config/nginx-reverse-proxy.conf`
- ✅ Nginx routes:
  - `/` → dashboard:80 (static files)
  - `/api/*` → oauth2-proxy:4180 → backend:8000
  - `/oauth2/*` → oauth2-proxy:4180
  - `/ws/*` → oauth2-proxy:4180 → backend:8000 (WebSocket)

### 2.3 Update Container Compose Files ✅ COMPLETED
- ✅ `podman-compose.yml` → replace with nginx architecture
- ✅ Dashboard: production build served by nginx (port 80 internal)
- ✅ Reverse proxy: nginx container handling all routing
- ✅ Single access point: `localhost:80`
- ✅ Build args for environment variables

## Phase 3: Update Makefile & Documentation

### 3.1 New Makefile Targets
```bash
make dev              # Simple: vite + uvicorn (no auth)
make container-test   # Nginx + all services (with auth) 
make container-clean  # Clean containers
```

### 3.2 Remove Obsolete Files
- Any oauth2-proxy dev configs
- Old nginx container configs  
- Unused environment files

## Implementation Status

### ✅ Phase 1: Clean Dev Environment - COMPLETED
✅ Removed `make dev-auth` and `make dev-auth-full` targets
✅ Removed `dev:auth` npm script
✅ Updated `dashboard/DEV_MODES.md` to reflect simplified approach
✅ Simplified `vite.config.ts` with dev vs container mode logic
✅ Updated backend CORS to include `localhost:5173`
✅ Clean separation: dev = simple, containers = auth
✅ Cleaned up `.env` files (removed `.env.auth`, updated `.env.development`)

### ✅ Phase 2: Nginx Container Setup - COMPLETED
Architecture: Browser → Nginx Reverse Proxy → {Dashboard nginx, OAuth2-proxy}
- ✅ Production React build served by nginx (not dev mode)
- ✅ Single nginx reverse proxy handles all routing
- ✅ Environment variables baked at build time

### ✅ Phase 3: Update Makefile & Documentation - COMPLETED
- ✅ Updated service names: `frontend` → `dashboard`, `tarsy-backend` → `backend`
- ✅ Updated container deployment URLs to reflect nginx reverse proxy
- ✅ Updated help text and build targets
- ✅ Cleaned up obsolete configuration files

## Files to Modify
- `Makefile`
- `podman-compose.yml`
- `dashboard/vite.config.ts`
- `dashboard/src/config/env.ts`
- `backend/tarsy/config/settings.py` (CORS)

## Files Created ✅
- ✅ `dashboard/nginx.conf` 
- ✅ `config/nginx-reverse-proxy.conf`

## Files Replaced ✅
- ✅ `dashboard/Dockerfile` (multi-stage production build)

## Files Deleted ✅ 
- ✅ `dashboard/.env.auth` (Phase 1)
- ⚠️ `dashboard/DEV_MODES.md` (user deleted manually)
- Any old nginx-related container configs (none existed)
