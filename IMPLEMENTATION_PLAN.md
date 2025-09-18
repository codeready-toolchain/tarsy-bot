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

## Phase 2: Container Setup with Traefik

### 2.1 Add Traefik Configuration
- Create `config/traefik.yml` (static config)
- Create `config/dynamic.yml` (routing rules)
- Replace nginx references with traefik in containers

### 2.2 Update Container Compose Files
- `podman-compose.yml` → add traefik service
- Frontend: keep `vite dev` mode for container testing
- Traefik routes:
  - `/` → frontend:3000
  - `/api/*` → oauth2-proxy:4180
  - `/oauth2/*` → oauth2-proxy:4180  
  - `/ws/*` → oauth2-proxy:4180

### 2.3 Update Frontend Container Config
- Remove hardcoded ports from frontend URLs
- Use relative URLs (let traefik handle routing)
- Single access point: `localhost:80`

## Phase 3: Update Makefile & Documentation

### 3.1 New Makefile Targets
```bash
make dev              # Simple: vite + uvicorn (no auth)
make container-test   # Traefik + all services (with auth)
make container-clean  # Clean containers
```

### 3.2 Remove Obsolete Files
- Any oauth2-proxy dev configs
- Old nginx container configs  
- Unused environment files

## Implementation Order
1. ✅ Phase 1 (clean dev) - COMPLETED
2. Phase 2 (traefik) - more complex, test carefully
3. Phase 3 (documentation) - cleanup

## Phase 1 Results - COMPLETED
✅ Removed `make dev-auth` and `make dev-auth-full` targets
✅ Removed `dev:auth` npm script
✅ Updated `dashboard/DEV_MODES.md` to reflect simplified approach
✅ Simplified `vite.config.ts` with dev vs container mode logic
✅ Updated backend CORS to include `localhost:5173`
✅ Clean separation: dev = simple, containers = auth

## Files to Modify
- `Makefile`
- `podman-compose.yml`
- `dashboard/vite.config.ts`
- `dashboard/src/config/env.ts`
- `backend/tarsy/config/settings.py` (CORS)

## Files to Create
- `config/traefik.yml`
- `config/traefik-dynamic.yml`

## Files to Delete
- `dashboard/.env.auth`
- `dashboard/DEV_MODES.md`
- Any nginx-related container configs
