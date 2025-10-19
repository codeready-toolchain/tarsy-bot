# Tarsy - Development Makefile
# ===================================

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m  
RED := \033[0;31m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Service ports
BACKEND_PORT := 8000
DASHBOARD_PORT := 5173

# Container management
PODMAN_COMPOSE := COMPOSE_PROJECT_NAME=tarsy podman compose -f deploy/podman-compose.yml

# Container environment
ROUTE_HOST ?= localhost:8080
COOKIE_SECURE ?= false

# OAuth2 configuration (must be set via environment variables)
# These should NEVER be committed to git!
# Auto-load from config/oauth.env if it exists
-include config/oauth.env.mk

# If config/oauth.env exists (shell format), convert it to make format
ifneq (,$(wildcard config/oauth.env))
    $(info 📝 Loading OAuth2 config from config/oauth.env)
    # Parse export statements and strip quotes
    OAUTH_ENV_VARS := $(shell sed -n 's/^export \([^=]*\)="\?\([^"]*\)"\?/\1=\2/p' config/oauth.env)
    $(foreach var,$(OAUTH_ENV_VARS),$(eval $(var)))
endif

OAUTH_CLIENT_ID ?= 
OAUTH_CLIENT_SECRET ?= 
GITHUB_ORG ?= 
GITHUB_TEAM ?=

# Prerequisites check
.PHONY: check-prereqs
check-prereqs: ## Check if required tools are installed
	@echo -e "$(BLUE)Checking prerequisites...$(NC)"
	@command -v python3 >/dev/null 2>&1 || (echo "$(RED)✗ Python 3 not found$(NC)" && exit 1)
	@command -v node >/dev/null 2>&1 || (echo "$(RED)✗ Node.js not found$(NC)" && exit 1)  
	@command -v npm >/dev/null 2>&1 || (echo "$(RED)✗ npm not found$(NC)" && exit 1)
	@command -v uv >/dev/null 2>&1 || (echo "$(RED)✗ uv not found. Install from: https://docs.astral.sh/uv/$(NC)" && exit 1)
	@echo -e "$(GREEN)✓ All prerequisites found$(NC)"

# Setup targets
.PHONY: setup
setup: check-prereqs ## Complete project setup (run this first!)
	@echo -e "$(GREEN)🚀 Setting up TARSy development environment...$(NC)"
	@echo -e "$(BLUE)Setting up backend...$(NC)"
	$(MAKE) -C backend install
	@if [ ! -f backend/.env ]; then \
		echo -e "$(YELLOW)Creating backend/.env from template...$(NC)"; \
		cp backend/env.template backend/.env; \
		echo -e "$(YELLOW)⚠️  IMPORTANT: Edit backend/.env with your API keys!$(NC)"; \
	else \
		echo -e "$(GREEN)✓ backend/.env already exists - keeping your configuration$(NC)"; \
	fi
	@echo -e "$(BLUE)Setting up dashboard...$(NC)"
	cd dashboard && npm install
	@echo -e "$(GREEN)✅ Setup completed! Run 'make dev' to start all services$(NC)"
	@echo ""
	@echo -e "$(YELLOW)Next steps:$(NC)"
	@echo "1. Edit backend/.env with your API keys"
	@echo "2. Run 'make dev' to start all services"
	@echo "3. Visit the URLs shown by 'make urls'"

# Development targets
.PHONY: dev
dev: ## Start all services for development (direct backend connection)
	@echo -e "$(GREEN)🚀 Starting all services in simplified dev mode...$(NC)"
	@echo -e "$(BLUE)Backend will run on: http://localhost:$(BACKEND_PORT)$(NC)"
	@echo -e "$(BLUE)Dashboard will run on: http://localhost:5173$(NC)"
	@echo -e "$(YELLOW)Mode: Direct backend connection (no containers, no auth)$(NC)"
	@echo ""
	@trap 'make stop' INT; \
	( \
		echo -e "$(YELLOW)Starting backend...$(NC)" && \
		(cd backend && make dev) & \
		echo -e "$(YELLOW)Starting dashboard...$(NC)" && \
		(cd dashboard && npm run dev) & \
		wait \
	)

# Individual service targets
.PHONY: backend
backend: ## Start backend only
	@echo -e "$(GREEN)Starting backend on http://localhost:$(BACKEND_PORT)$(NC)"
	$(MAKE) -C backend dev

.PHONY: dashboard
dashboard: ## Start dashboard only (direct backend connection)
	@echo -e "$(GREEN)Starting dashboard on http://localhost:$(DASHBOARD_PORT)$(NC)"
	@echo -e "$(YELLOW)Direct backend connection to localhost:$(BACKEND_PORT)$(NC)"
	cd dashboard && npm run dev

# Stop services
.PHONY: stop
stop: ## Stop all running services
	@echo -e "$(YELLOW)Stopping all services...$(NC)"
	$(MAKE) -C backend stop
	@lsof -ti:$(DASHBOARD_PORT) | xargs -r kill -9 2>/dev/null || true
	@echo -e "$(GREEN)✅ All services stopped$(NC)"

# Container deployment targets
# 
# Quick guide:
# - containers-deploy:       Normal deployment (uses cache, fast but may miss code changes)
# - containers-redeploy:     Force rebuild without cache (slower but guarantees fresh code)
# - containers-rebuild:      Just rebuild images without redeploying
# - containers-deploy-fresh: Nuclear option (rebuilds everything including database)
#
.PHONY: containers-build-app containers-rebuild containers-deploy containers-redeploy containers-deploy-fresh containers-start containers-stop containers-clean containers-clean-images containers-deep-clean containers-db-reset check-config containers-logs containers-status sync-backend-deps

sync-backend-deps: ## Sync backend dependencies (update uv.lock if pyproject.toml changed)
	@echo -e "$(GREEN)Syncing backend dependencies...$(NC)"
	@cd backend && uv sync
	@echo -e "$(GREEN)✅ Backend dependencies synced$(NC)"

containers-build-app: sync-backend-deps ## Build only application containers (backend, dashboard) - preserves database
	@echo -e "$(GREEN)Building Tarsy application container images (preserving database)...$(NC)"
	$(PODMAN_COMPOSE) build backend dashboard
	@echo -e "$(GREEN)✅ Application container images built$(NC)"

containers-rebuild: sync-backend-deps ## Force rebuild application containers without cache (for code changes)
	@echo -e "$(YELLOW)⚡ Force rebuilding application containers (no cache)...$(NC)"
	@echo -e "$(YELLOW)Removing old application images...$(NC)"
	-podman rmi -f localhost/tarsy_backend localhost/tarsy_dashboard 2>/dev/null || true
	@echo -e "$(GREEN)Building fresh images...$(NC)"
	$(PODMAN_COMPOSE) build --no-cache backend dashboard
	@echo -e "$(GREEN)✅ Application containers rebuilt from scratch$(NC)"

check-config: ## Ensure required configuration files exist (internal target)
	@echo -e "$(GREEN)Checking configuration files...$(NC)"
	@if [ ! -f backend/.env ]; then \
		echo -e "$(RED)❌ Error: backend/.env file not found$(NC)"; \
		echo -e "$(YELLOW)Please create backend/.env with your API keys and settings$(NC)"; \
		exit 1; \
	fi
	@if [ ! -d config ]; then \
		echo -e "$(RED)❌ Error: config/ directory not found$(NC)"; \
		echo -e "$(YELLOW)Please ensure config/ directory exists with required files$(NC)"; \
		exit 1; \
	fi
	@if [ ! -f config/oauth2-proxy-container.cfg.template ]; then \
		echo -e "$(RED)❌ Error: config/oauth2-proxy-container.cfg.template not found$(NC)"; \
		echo -e "$(YELLOW)Please ensure the template file exists$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(BLUE)Checking OAuth2 environment variables...$(NC)"
	@if [ -z "$(OAUTH_CLIENT_ID)" ]; then \
		echo -e "$(RED)❌ Error: OAUTH_CLIENT_ID not set$(NC)"; \
		echo -e "$(YELLOW)Please export OAUTH_CLIENT_ID=your-client-id$(NC)"; \
		echo -e "$(YELLOW)See config/README.md for setup instructions$(NC)"; \
		exit 1; \
	fi
	@if [ -z "$(OAUTH_CLIENT_SECRET)" ]; then \
		echo -e "$(RED)❌ Error: OAUTH_CLIENT_SECRET not set$(NC)"; \
		echo -e "$(YELLOW)Please export OAUTH_CLIENT_SECRET=your-secret$(NC)"; \
		exit 1; \
	fi
	@if [ -z "$(GITHUB_ORG)" ]; then \
		echo -e "$(YELLOW)⚠️  Warning: GITHUB_ORG not set, using placeholder$(NC)"; \
	fi
	@if [ -z "$(GITHUB_TEAM)" ]; then \
		echo -e "$(YELLOW)⚠️  Warning: GITHUB_TEAM not set, using placeholder$(NC)"; \
	fi
	@echo -e "$(BLUE)Generating OAuth2-proxy config from template...$(NC)"
	@sed -e 's|{{ROUTE_HOST}}|$(ROUTE_HOST)|g' \
	     -e 's|{{COOKIE_SECURE}}|$(COOKIE_SECURE)|g' \
	     -e 's|{{OAUTH_CLIENT_ID}}|$(OAUTH_CLIENT_ID)|g' \
	     -e 's|{{OAUTH_CLIENT_SECRET}}|$(OAUTH_CLIENT_SECRET)|g' \
	     -e 's|{{GITHUB_ORG}}|$(or $(GITHUB_ORG),your-org)|g' \
	     -e 's|{{GITHUB_TEAM}}|$(or $(GITHUB_TEAM),your-team)|g' \
	     config/oauth2-proxy-container.cfg.template > config/oauth2-proxy-container.cfg
	@echo -e "$(GREEN)✅ OAuth2-proxy config generated for $(ROUTE_HOST)$(NC)"
	@echo -e "$(GREEN)✅ Configuration files ready$(NC)"

containers-deploy: check-config ## Deploy Tarsy stack (smart default: rebuild apps, preserve database)
	@echo -e "$(GREEN)Deploying Tarsy application stack (preserving database)...$(NC)"
	@echo -e "$(YELLOW)Stopping all containers...$(NC)"
	-$(PODMAN_COMPOSE) down 2>/dev/null || true
	@echo -e "$(YELLOW)Building and starting all containers...$(NC)"
	$(PODMAN_COMPOSE) up -d --build
	@echo ""
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(BLUE)🌐 Dashboard:          http://localhost:8080$(NC)"
	@echo -e "$(BLUE)🔧 API (oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo -e "$(BLUE)🗄️  Database (admin):   localhost:5432$(NC)"
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(GREEN)✅ Application deployment completed$(NC)"

containers-redeploy: containers-rebuild check-config ## Force rebuild and redeploy (for code changes)
	@echo -e "$(YELLOW)Stopping all containers...$(NC)"
	-$(PODMAN_COMPOSE) down 2>/dev/null || true
	@echo -e "$(YELLOW)Ensuring no orphaned containers...$(NC)"
	-@if podman ps -aq --filter "name=tarsy" --filter "name=deploy" | grep -q .; then \
		podman rm -f $$(podman ps -aq --filter "name=tarsy" --filter "name=deploy") 2>/dev/null || true; \
	fi
	@echo -e "$(GREEN)Starting containers with fresh images...$(NC)"
	$(PODMAN_COMPOSE) up -d
	@echo ""
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(BLUE)🌐 Dashboard:          http://localhost:8080$(NC)"
	@echo -e "$(BLUE)🔧 API (oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo -e "$(BLUE)🗄️  Database (admin):   localhost:5432$(NC)"
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(GREEN)✅ Force redeploy completed$(NC)"

containers-hard-redeploy: containers-kill-all containers-rebuild check-config ## Nuclear option: kill all Tarsy containers and redeploy
	@echo -e "$(GREEN)Starting fresh deployment...$(NC)"
	$(PODMAN_COMPOSE) up -d
	@echo ""
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(BLUE)🌐 Dashboard:          http://localhost:8080$(NC)"
	@echo -e "$(BLUE)🔧 API (oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo -e "$(BLUE)🗄️  Database (admin):   localhost:5432$(NC)"
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(GREEN)✅ Hard redeploy completed (all Tarsy containers killed and recreated)$(NC)"

containers-deploy-fresh: containers-clean check-config ## Deploy complete fresh Tarsy stack (rebuild everything including database)
	@echo -e "$(GREEN)Starting complete fresh Tarsy container stack...$(NC)"
	$(PODMAN_COMPOSE) up -d --build
	@echo ""
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(BLUE)🌐 Dashboard:          http://localhost:8080$(NC)"
	@echo -e "$(BLUE)🔧 API (oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo -e "$(BLUE)🗄️  Database (admin):   localhost:5432$(NC)"
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(GREEN)✅ Fresh deployment completed$(NC)"

containers-start: ## Start containers (quick restart after stop)
	@echo -e "$(GREEN)Starting Tarsy container stack...$(NC)"
	$(PODMAN_COMPOSE) up -d
	@echo ""
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(BLUE)🌐 Dashboard:          http://localhost:8080$(NC)"
	@echo -e "$(BLUE)🔧 API (oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo -e "$(BLUE)🗄️  Database (admin):   localhost:5432$(NC)"
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo -e "$(GREEN)✅ Containers started$(NC)"

containers-stop: ## Stop all running containers
	@echo -e "$(YELLOW)Stopping containers...$(NC)"
	-$(PODMAN_COMPOSE) down 2>/dev/null || true
	@echo -e "$(GREEN)✅ Containers stopped$(NC)"

containers-kill-all: ## Force stop and remove ALL Tarsy-related containers (both tarsy-* and deploy_*)
	@echo -e "$(YELLOW)Stopping and removing all Tarsy-related containers...$(NC)"
	@if podman ps -aq --filter "name=tarsy" | grep -q .; then \
		echo -e "$(YELLOW)Removing tarsy-* containers...$(NC)"; \
		podman rm -f $$(podman ps -aq --filter "name=tarsy") 2>/dev/null || true; \
	fi
	@if podman ps -aq --filter "name=deploy" | grep -q .; then \
		echo -e "$(YELLOW)Removing deploy_* containers...$(NC)"; \
		podman rm -f $$(podman ps -aq --filter "name=deploy") 2>/dev/null || true; \
	fi
	@echo -e "$(GREEN)✅ All Tarsy containers removed$(NC)"

containers-clean: containers-stop ## Stop and remove all containers, networks, and volumes
	@echo -e "$(YELLOW)Cleaning up containers, networks, and volumes...$(NC)"
	-podman system prune -f 2>/dev/null || true
	@echo -e "$(GREEN)✅ Container cleanup completed$(NC)"

containers-clean-images: ## Remove all project-related container images (aggressive cleanup)
	@echo -e "$(YELLOW)Removing all Tarsy container images...$(NC)"
	@echo -e "$(RED)⚠️  This will require rebuilding images on next deployment$(NC)"
	-podman images --filter "reference=tarsy*" --format "{{.Repository}}:{{.Tag}}" | xargs -r podman rmi -f 2>/dev/null || true
	-podman images --filter "reference=localhost/tarsy*" --format "{{.Repository}}:{{.Tag}}" | xargs -r podman rmi -f 2>/dev/null || true
	@echo -e "$(GREEN)✅ Project images removed$(NC)"

containers-deep-clean: containers-clean containers-clean-images ## Complete cleanup: containers, volumes, networks, and all images
	@echo -e "$(YELLOW)Removing database volumes...$(NC)"
	-podman volume rm tarsy-bot_postgres_data tarsy_postgres_data 2>/dev/null || true
	@echo -e "$(GREEN)✅ Deep cleanup completed - everything removed$(NC)"

containers-db-reset: ## Reset database volume (fixes PostgreSQL version conflicts)
	@echo -e "$(YELLOW)⚠️  This will delete all database data!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo -e "$(YELLOW)Stopping database container...$(NC)"; \
			-$(PODMAN_COMPOSE) stop database 2>/dev/null || true; \
			echo -e "$(YELLOW)Removing database volume...$(NC)"; \
			-podman volume rm tarsy-bot_postgres_data 2>/dev/null || true; \
			-podman volume rm tarsy_postgres_data 2>/dev/null || true; \
			echo -e "$(YELLOW)Starting fresh database...$(NC)"; \
			$(PODMAN_COMPOSE) up -d database; \
			echo -e "$(GREEN)✅ Database volume reset completed$(NC)"; \
			;; \
		*) \
			echo -e "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

containers-logs: ## Show logs from all running containers
	@echo -e "$(GREEN)Container logs:$(NC)"
	@$(PODMAN_COMPOSE) logs --tail=50 || echo "No containers running"

containers-status: ## Show container status
	@echo -e "$(GREEN)Container status:$(NC)"
	-podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No containers running"

# Build targets
.PHONY: build
build: ## Build for production
	@echo -e "$(GREEN)Building all components...$(NC)"
	cd dashboard && npm run build
	@echo -e "$(GREEN)✅ Build completed$(NC)"

# Status and info targets
.PHONY: status
status: ## Show which services are running and project status
	@echo -e "$(GREEN)TARSy Service Status$(NC)"
	@echo "=========================="
	@echo "Backend (port $(BACKEND_PORT)): $$(if lsof -i:$(BACKEND_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo "Dashboard (port $(DASHBOARD_PORT)): $$(if lsof -i:$(DASHBOARD_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo ""
	$(MAKE) -C backend status

.PHONY: urls
urls: ## Display service URLs and endpoints
	@echo -e "$(GREEN)TARSy Service URLs$(NC)"
	@echo "======================"
	@echo -e "$(BLUE)🌍 Frontend Applications:$(NC)"
	@echo "  SRE Dashboard:   http://localhost:$(DASHBOARD_PORT)"
	@echo "    - Manual Alert Submission: http://localhost:$(DASHBOARD_PORT)/submit-alert"
	@echo ""
	@echo -e "$(BLUE)🔧 Backend Services:$(NC)"
	@echo "  API Server:      http://localhost:$(BACKEND_PORT)"
	@echo "  API Docs:        http://localhost:$(BACKEND_PORT)/docs"
	@echo "  Health Check:    http://localhost:$(BACKEND_PORT)/health"

.PHONY: logs
logs: ## Show recent logs from all services
	$(MAKE) -C backend logs
