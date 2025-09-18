# EP-0019: Docker Deployment Infrastructure - Design Document

**Created:** 2025-09-17  

---

## Design Overview

This enhancement introduces comprehensive Docker deployment infrastructure for Tarsy using podman and podman-compose. The design provides containerized deployment options for development, testing, and production environments with proper service orchestration and persistent storage.

### Architecture Summary

The Docker deployment provides:
1. **Complete Container Stack**: Backend, frontend, database, and oauth2-proxy authentication in containers
2. **Authenticated by Default**: All containerized services protected by oauth2-proxy authentication layer
3. **Podman-Based**: Uses podman and podman-compose for container orchestration
4. **Mirror Registry**: Uses mirror.gcr.io to avoid Docker Hub rate limits
5. **Alternative to Local**: Complements existing local development options with full containerization
6. **Make Integration**: Consistent with existing development workflow

### Key Design Principles

- **Podman Native**: Uses podman ecosystem for container management
- **Complete Stack**: All services (backend, frontend, database, oauth2-proxy) containerized
- **Authenticated Access**: oauth2-proxy provides secure access to all services
- **Mirror Registry**: Avoids Docker Hub rate limits and dependency issues
- **Make Workflow**: Integrates with existing Makefile-based development workflow
- **Service Isolation**: Each component runs in its own container
- **Persistent Storage**: Proper volume management for data persistence
- **Alternative Option**: Provides containerized alternative to existing local development

## System Architecture

### Component Architecture

#### New Components

- **Container Images**: Dockerfile definitions for backend and frontend services
- **Complete Service Stack**: Database, backend, frontend, and oauth2-proxy in containers
- **Podman Compose**: Service orchestration and networking configuration for full stack
- **Volume Management**: Persistent storage for database, application data, and logs
- **Registry Configuration**: Mirror registry setup for reliable image pulls

#### Modified Components

- **Root Makefile**: Extended with container deployment targets
- **Build Process**: Containerized build pipeline for both services
- **Development Workflow**: Container-based development options

#### Component Interactions

1. Developer runs `make deploy-containers` for full containerized stack
2. Podman builds images from Dockerfiles using mirror.gcr.io base images
3. Podman-compose orchestrates all services (database, backend, frontend, oauth2-proxy)
4. oauth2-proxy handles authentication for backend API requests only (port 4180)
5. Frontend accessible directly, backend only accessible through oauth2-proxy
6. Frontend makes API calls to oauth2-proxy which forwards to backend
6. Database runs in container with persistent storage
7. Volumes are mounted for persistent data storage
8. Services communicate via container networking
9. Make targets provide management interface for containers

## Configuration Design

### Container Images

#### Base Images (using mirror.gcr.io)
```yaml
# Use Google Container Registry mirror instead of Docker Hub
python: mirror.gcr.io/library/python:3.13-slim
node: mirror.gcr.io/library/node:20-alpine
```

### Podman Compose Configuration

#### Complete Containerized Stack
```yaml
# podman-compose.yml
version: '3.8'
services:
  database:
    image: mirror.gcr.io/library/postgres:16
    environment:
      - POSTGRES_DB=tarsy
      - POSTGRES_USER=tarsy
      - POSTGRES_PASSWORD=tarsy-dev-password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"  # For debugging/admin access only
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tarsy"]
      interval: 30s
      timeout: 10s
      retries: 5

  oauth2-proxy:
    image: quay.io/oauth2-proxy/oauth2-proxy:v7.5.1
    command:
      - --http-address=0.0.0.0:4180
      - --upstream=http://tarsy-backend:8000
      - --email-domain=*
      - --cookie-secret=change-me-in-production
      - --client-id=your-client-id
      - --client-secret=your-client-secret
      - --provider=github  # or google, oidc, etc.
      - --skip-auth-route=GET=^/$
      - --skip-auth-route=GET=^/api/v1/history/health
      - --skip-auth-route=GET=^/health
      - --api-route=^/api
      - --api-route=^/alerts
      - --api-route=^/alert-types
      - --api-route=^/session-id
      - --api-route=^/ws
    ports:
      - "4180:4180"  # API proxy endpoint
    depends_on:
      - tarsy-backend
    environment:
      - OAUTH2_PROXY_COOKIE_SECRET=change-me-in-production
      - OAUTH2_PROXY_CLIENT_ID=your-client-id
      - OAUTH2_PROXY_CLIENT_SECRET=your-client-secret

  tarsy-backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    # No direct port exposure - only accessible through oauth2-proxy
    environment:
      - HISTORY_ENABLED=true
      - DATABASE_URL=postgresql://tarsy:tarsy-dev-password@database:5432/tarsy
    volumes:
      - ./.env:/app/.env:ro                        # Mount environment variables
      - ./config:/app/config:ro                    # Mount configuration files
      - ./data:/app/data                           # Persist application data
      - ./logs:/app/logs                           # Persist logs
    depends_on:
      database:
        condition: service_healthy
    
  tarsy-frontend:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    ports:
      - "3000:3000"  # Direct frontend access
    environment:
      - VITE_API_BASE_URL=http://localhost:4180  # Frontend calls API through oauth2-proxy
      - VITE_WS_BASE_URL=ws://localhost:4180     # WebSocket connections through oauth2-proxy
    depends_on:
      - oauth2-proxy

volumes:
  postgres_data:
```

### Configuration Management

#### Volume-Based Configuration

The containerized deployment uses volume mounts to provide configuration files to the backend service:

```yaml
volumes:
  - ./.env:/app/.env:ro                        # Environment variables (API keys, database URLs)
  - ./config:/app/config:ro                    # Configuration files (agents.yaml, llm_providers.yaml)
  - ./data:/app/data                          # Persistent application data
  - ./logs:/app/logs                          # Persistent logs
```

#### Configuration Files

**`.env`** - Environment variables:
- API keys (Google, OpenAI, GitHub, etc.)
- Database connection strings
- Feature flags and runtime settings

**`config/agents.yaml`** - Agent and MCP server configuration:
- Custom agent definitions
- MCP server connections
- Agent routing rules

**`config/llm_providers.yaml`** - LLM provider settings:
- Custom LLM provider configurations
- Model overrides and parameters

#### Benefits of Volume Mounts

1. **Security**: No secrets baked into container images
2. **Portability**: Same image works across environments
3. **Registry Safe**: Images can be pushed to external registries safely
4. **Runtime Configuration**: Config changes without rebuilding images
5. **Environment Specific**: Each deployment uses its own configuration files

#### Image vs Runtime Separation

**Built into Image**:
- Application code
- Python dependencies
- Default configuration templates

**Provided at Runtime**:
- Environment-specific settings (`.env`)
- Agent configurations (`config/agents.yaml`)
- LLM provider settings (`config/llm_providers.yaml`)

### Container Dockerfiles

#### Backend Dockerfile
```dockerfile
# backend/Dockerfile
FROM mirror.gcr.io/library/python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run application using make
CMD ["make", "run"]
```

#### Frontend Dockerfile
```dockerfile
# dashboard/Dockerfile
FROM mirror.gcr.io/library/node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Copy source code
COPY . .

# Install dependencies
RUN npm ci --only=production

# Build application
RUN npm run build

# Expose port
EXPOSE 3000

# Serve application
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0"]
```

### OAuth2 Proxy Integration

#### Integrated Authentication Layer

The existing oauth2-proxy authentication layer is always included in the containerized deployment. This provides API authentication and authorization capabilities that are available in the current system, ensuring the backend API is properly secured while allowing direct frontend access.

#### Deployment Options

The system provides two distinct deployment approaches:

1. **Local Development** (existing): Use `make dev`, `make dev-full`, `make dev-full-auth`, etc. for local development with optional authentication
2. **Containerized Deployment** (new): Use `make deploy-containers` for complete containerized stack with integrated authentication

This separation allows developers to choose between local development flexibility and containerized consistency with built-in security.

#### Routing Configuration

```yaml
# oauth2-proxy routing configuration
upstreams:
  - http://tarsy-backend:8000    # Backend API endpoints only
```

**Important**: The frontend is NOT proxied through oauth2-proxy. Instead:
- Frontend runs directly accessible on port 3000
- Frontend makes API calls to oauth2-proxy on port 4180 
- oauth2-proxy forwards authenticated API requests to backend on port 8000

#### Provider Configuration Options

##### GitHub Provider
```yaml
environment:
  - OAUTH2_PROXY_PROVIDER=github
  - OAUTH2_PROXY_CLIENT_ID=your-github-client-id
  - OAUTH2_PROXY_CLIENT_SECRET=your-github-client-secret
  - OAUTH2_PROXY_GITHUB_ORG=your-organization  # Optional: restrict to org
```

##### Google Provider
```yaml
environment:
  - OAUTH2_PROXY_PROVIDER=google
  - OAUTH2_PROXY_CLIENT_ID=your-google-client-id
  - OAUTH2_PROXY_CLIENT_SECRET=your-google-client-secret
  - OAUTH2_PROXY_EMAIL_DOMAIN=your-domain.com  # Optional: restrict domain
```

##### OIDC Provider
```yaml
environment:
  - OAUTH2_PROXY_PROVIDER=oidc
  - OAUTH2_PROXY_CLIENT_ID=your-oidc-client-id
  - OAUTH2_PROXY_CLIENT_SECRET=your-oidc-client-secret
  - OAUTH2_PROXY_OIDC_ISSUER_URL=https://your-oidc-provider.com
```

#### Security Configuration

```yaml
environment:
  # Cookie configuration
  - OAUTH2_PROXY_COOKIE_SECRET=generate-a-32-byte-secret
  - OAUTH2_PROXY_COOKIE_SECURE=true        # Enable in production
  - OAUTH2_PROXY_COOKIE_HTTPONLY=true
  
  # Session configuration
  - OAUTH2_PROXY_SESSION_STORE_TYPE=cookie
  - OAUTH2_PROXY_COOKIE_EXPIRE=24h
  
  # Access control
  - OAUTH2_PROXY_EMAIL_DOMAIN=*           # Allow all domains or specify
  - OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE=/etc/oauth2_proxy/emails.txt
```

#### Network Flow

```
User Browser Access → tarsy-frontend:3000 (Direct Access)
                                 ↓
Frontend API Calls → oauth2-proxy:4180 → Authentication Check
                                        ↓
                                  [If Authenticated]
                                        ↓
                                 tarsy-backend:8000
                                 (Internal Only)
```

## Implementation Design

### Make Targets

Add these targets to the root Makefile to support container deployment:

```makefile
# Container deployment targets
.PHONY: build-images deploy-containers stop-containers clean-containers

build-images: ## Build all container images with podman
	@echo "$(GREEN)Building Tarsy container images...$(NC)"
	podman build -t tarsy-backend:latest ./backend
	podman build -t tarsy-frontend:latest ./dashboard
	@echo "$(GREEN)✅ Container images built$(NC)"

deploy-containers: build-images check-config ## Deploy complete Tarsy stack with database and authentication
	@echo "$(GREEN)Deploying complete Tarsy container stack...$(NC)"
	podman-compose -f podman-compose.yml up -d
	@echo "$(BLUE)Frontend: http://localhost:3000$(NC)"
	@echo "$(BLUE)API (via oauth2-proxy): http://localhost:4180$(NC)"
	@echo "$(BLUE)Database (admin access): localhost:5432$(NC)"
	@echo "$(YELLOW)Note: Backend API secured behind oauth2-proxy authentication$(NC)"

check-config: ## Ensure required configuration files exist (internal target)
	@echo "$(GREEN)Checking configuration files...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(RED)❌ Error: .env file not found$(NC)"; \
		echo "$(YELLOW)Please create .env with your API keys and settings$(NC)"; \
		exit 1; \
	fi
	@if [ ! -d config ]; then \
		echo "$(RED)❌ Error: config/ directory not found$(NC)"; \
		echo "$(YELLOW)Please ensure config/ directory exists with required files$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)✅ Configuration files found$(NC)"

stop-containers: ## Stop all running containers
	@echo "$(YELLOW)Stopping containers...$(NC)"
	-podman-compose -f podman-compose.yml down 2>/dev/null || true
	@echo "$(GREEN)✅ Containers stopped$(NC)"

clean-containers: ## Remove containers, networks, and volumes
	@echo "$(YELLOW)Cleaning up containers and volumes...$(NC)"
	-podman-compose -f podman-compose.yml down -v 2>/dev/null || true
	-podman system prune -f 2>/dev/null || true
	@echo "$(GREEN)✅ Container cleanup completed$(NC)"

container-logs: ## Show logs from all running containers
	@echo "$(GREEN)Container logs:$(NC)"
	-podman-compose logs --tail=50 2>/dev/null || echo "No containers running"

container-status: ## Show container status
	@echo "$(GREEN)Container status:$(NC)"
	-podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No containers running"
```

## Testing Strategy

### Container Testing

#### Unit Testing
```bash
# Test container builds
make build-images

# Verify images created
podman images | grep tarsy

# Test basic container startup
podman run --rm -p 8000:8000 tarsy-backend:latest &
sleep 5
curl http://localhost:8000/health
```

#### Integration Testing

**Prerequisites**: Ensure configuration files exist:
- `.env` file with API keys and database settings
- `config/` directory with `agents.yaml` and `llm_providers.yaml`

```bash
# Deploy complete containerized stack (includes config validation)
make deploy-containers

# Test frontend direct access
curl http://localhost:3000  # Should work - frontend directly accessible

# Test database connectivity (for admin/debugging)
psql -h localhost -U tarsy -d tarsy  # Should connect

# Test oauth2-proxy API access (will redirect to auth provider for unauthenticated requests)
curl -I http://localhost:4180/api/v1/history/health

# Test authenticated API access (requires browser session or token)
curl -H "Authorization: Bearer <token>" http://localhost:4180/api/v1/history/health

# Test backend isolation (should fail - backend not directly accessible)
curl http://localhost:8000/health  # Should fail - not exposed

# Test database admin access
pg_isready -h localhost -U tarsy  # Should work - admin access available

# Cleanup
make clean-containers
```

### Development Workflow

#### Container Development
```bash
# Build and deploy containers
make deploy-containers

# Check application status
make status

# View container logs
make container-logs

# Check container status
make container-status

# Stop when done
make stop-containers
```

#### Debugging Containers
```bash
# Access backend container
podman exec -it $(podman ps -q --filter ancestor=tarsy-backend:latest) bash

# Access frontend container
podman exec -it $(podman ps -q --filter ancestor=tarsy-frontend:latest) sh

# View specific service logs
podman-compose logs -f tarsy-backend
podman-compose logs -f tarsy-frontend
```

## Error Handling & Resilience

### Container Error Handling

```bash
# Container health checks
podman ps --filter "status=exited" --filter "status=dead"

# Service restart
podman-compose restart tarsy-backend

# Full service recovery
make clean-containers
make deploy-containers
```

### Build Error Handling

```bash
# Clean build (no cache)
podman build --no-cache -t tarsy-backend:latest ./backend

# Force rebuild
podman rmi tarsy-backend:latest tarsy-frontend:latest
make build-images
```

## Documentation Requirements

### Configuration Documentation

- Container deployment guide
- Make target reference
- Troubleshooting common container issues
- Port and volume configuration

---

## Implementation Checklist

### Phase 1: Core Container Infrastructure
- [ ] Create Dockerfiles for backend and frontend using mirror.gcr.io base images
- [ ] Set up complete podman-compose configuration (database, backend, frontend, oauth2-proxy)
- [ ] Configure volume mounts for .env and config/ files
- [ ] Configure database container with persistent storage
- [ ] Integrate oauth2-proxy authentication for backend API access
- [ ] Add make targets for containerized deployment (including config validation)
- [ ] Test complete stack deployment and service interactions

### Phase 2: Development Integration
- [ ] Integrate with existing development workflow
- [ ] Test container networking and service communication

### Phase 3: Documentation
- [ ] Document container deployment process

---
