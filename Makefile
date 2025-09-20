# Tarsy - Development Makefile
# ===================================

.DEFAULT_GOAL := help

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m  
RED := \033[0;31m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Service ports
BACKEND_PORT := 8000
DASHBOARD_PORT := 5173

# Prerequisites check
.PHONY: check-prereqs
check-prereqs: ## Check if required tools are installed
	@echo "$(BLUE)Checking prerequisites...$(NC)"
	@command -v python3 >/dev/null 2>&1 || (echo "$(RED)✗ Python 3 not found$(NC)" && exit 1)
	@command -v node >/dev/null 2>&1 || (echo "$(RED)✗ Node.js not found$(NC)" && exit 1)  
	@command -v npm >/dev/null 2>&1 || (echo "$(RED)✗ npm not found$(NC)" && exit 1)
	@command -v uv >/dev/null 2>&1 || (echo "$(RED)✗ uv not found. Install from: https://docs.astral.sh/uv/$(NC)" && exit 1)
	@echo "$(GREEN)✓ All prerequisites found$(NC)"

# Setup targets
.PHONY: setup
setup: check-prereqs ## Complete project setup (run this first!)
	@echo "$(GREEN)🚀 Setting up TARSy development environment...$(NC)"
	@echo "$(BLUE)Setting up backend...$(NC)"
	$(MAKE) -C backend install
	@if [ ! -f backend/.env ]; then \
		echo "$(YELLOW)Creating backend/.env from template...$(NC)"; \
		cp backend/env.template backend/.env; \
		echo "$(YELLOW)⚠️  IMPORTANT: Edit backend/.env with your API keys!$(NC)"; \
	else \
		echo "$(GREEN)✓ backend/.env already exists - keeping your configuration$(NC)"; \
	fi
	@echo "$(BLUE)Setting up dashboard...$(NC)"
	cd dashboard && npm install
	@echo "$(GREEN)✅ Setup completed! Run 'make dev' to start all services$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "1. Edit backend/.env with your API keys"
	@echo "2. Run 'make dev' to start all services"
	@echo "3. Visit the URLs shown by 'make urls'"

# Development targets
.PHONY: dev
dev: ## Start all services for development (direct backend connection)
	@echo "$(GREEN)🚀 Starting all services in simplified dev mode...$(NC)"
	@echo "$(BLUE)Backend will run on: http://localhost:$(BACKEND_PORT)$(NC)"
	@echo "$(BLUE)Dashboard will run on: http://localhost:5173$(NC)"
	@echo "$(YELLOW)Mode: Direct backend connection (no containers, no auth)$(NC)"
	@echo ""
	@trap 'make stop' INT; \
	( \
		echo "$(YELLOW)Starting backend...$(NC)" && \
		(cd backend && make dev) & \
		echo "$(YELLOW)Starting dashboard...$(NC)" && \
		(cd dashboard && npm run dev) & \
		wait \
	)

# Individual service targets
.PHONY: backend
backend: ## Start backend only
	@echo "$(GREEN)Starting backend on http://localhost:$(BACKEND_PORT)$(NC)"
	$(MAKE) -C backend dev

.PHONY: dashboard
dashboard: ## Start dashboard only (direct backend connection)
	@echo "$(GREEN)Starting dashboard on http://localhost:$(DASHBOARD_PORT)$(NC)"
	@echo "$(YELLOW)Direct backend connection to localhost:$(BACKEND_PORT)$(NC)"
	cd dashboard && npm run dev

# Stop services
.PHONY: stop
stop: ## Stop all running services
	@echo "$(YELLOW)Stopping all services...$(NC)"
	$(MAKE) -C backend stop
	@lsof -ti:$(DASHBOARD_PORT) | xargs -r kill -9 2>/dev/null || true
	@echo "$(GREEN)✅ All services stopped$(NC)"

# Container deployment targets
.PHONY: containers-build containers-build-app containers-deploy containers-deploy-fresh containers-restart-app containers-start containers-start-fast containers-stop containers-clean check-config containers-logs containers-status

containers-build: ## Build all container images with podman-compose
	@echo "$(GREEN)Building Tarsy container images...$(NC)"
	@echo "$(YELLOW)Note: Using podman-compose for consistent builds with proper build arguments$(NC)"
	COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml build
	@echo "$(GREEN)✅ Container images built$(NC)"

containers-build-app: ## Build only application containers (backend, dashboard) - preserves database
	@echo "$(GREEN)Building Tarsy application container images (preserving database)...$(NC)"
	COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml build backend dashboard
	@echo "$(GREEN)✅ Application container images built$(NC)"

check-config: ## Ensure required configuration files exist (internal target)
	@echo "$(GREEN)Checking configuration files...$(NC)"
	@if [ ! -f backend/.env ]; then \
		echo "$(RED)❌ Error: backend/.env file not found$(NC)"; \
		echo "$(YELLOW)Please create backend/.env with your API keys and settings$(NC)"; \
		exit 1; \
	fi
	@if [ ! -d config ]; then \
		echo "$(RED)❌ Error: config/ directory not found$(NC)"; \
		echo "$(YELLOW)Please ensure config/ directory exists with required files$(NC)"; \
		exit 1; \
	fi
	@if [ ! -f config/oauth2-proxy-container.cfg ]; then \
		if [ -f config/oauth2-proxy.cfg ]; then \
			echo "$(YELLOW)📋 oauth2-proxy-container.cfg not found. Creating from oauth2-proxy.cfg...$(NC)"; \
			echo "$(YELLOW)⚠️  You may need to adjust container networking addresses$(NC)"; \
			cp config/oauth2-proxy.cfg config/oauth2-proxy-container.cfg; \
			echo "$(GREEN)✅ Created config/oauth2-proxy-container.cfg$(NC)"; \
		elif [ -f config/oauth2-proxy-container.cfg.example ]; then \
			echo "$(YELLOW)📋 oauth2-proxy-container.cfg not found. Creating from example...$(NC)"; \
			cp config/oauth2-proxy-container.cfg.example config/oauth2-proxy-container.cfg; \
			echo "$(GREEN)✅ Created config/oauth2-proxy-container.cfg from example$(NC)"; \
			echo "$(YELLOW)⚠️  Please review and adjust container networking addresses$(NC)"; \
		else \
			echo "$(RED)❌ Error: config/oauth2-proxy-container.cfg not found$(NC)"; \
			echo "$(YELLOW)Please create config/oauth2-proxy-container.cfg$(NC)"; \
			exit 1; \
		fi; \
	fi
	@echo "$(GREEN)✅ Configuration files found$(NC)"

containers-deploy: check-config containers-restart-app ## Deploy Tarsy stack (rebuild apps, preserve database)

containers-deploy-fresh: containers-clean check-config containers-start ## Deploy complete fresh Tarsy stack (rebuild everything including database)

containers-start: ## Start all running containers (with fresh build)
	@echo "$(GREEN)Starting complete Tarsy container stack...$(NC)"
	COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml up -d --build
	@echo "$(BLUE)Dashboard: http://localhost:8080$(NC)"
	@echo "$(BLUE)API (via oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo "$(BLUE)Database (admin access): localhost:5432$(NC)"
	@echo "$(YELLOW)Note: All traffic routed through nginx reverse proxy with oauth2-proxy authentication$(NC)"

containers-restart-app: ## Restart application containers (preserve database)
	@echo "$(GREEN)Restarting application containers (preserving database)...$(NC)"
	@echo "$(YELLOW)Stopping application containers...$(NC)"
	-COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml stop reverse-proxy oauth2-proxy backend dashboard 2>/dev/null || true
	@echo "$(YELLOW)Removing application containers...$(NC)"
	-COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml rm -f reverse-proxy oauth2-proxy backend dashboard 2>/dev/null || true
	@echo "$(YELLOW)Building and starting application containers...$(NC)"
	COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml up -d --build backend dashboard oauth2-proxy reverse-proxy
	@echo "$(BLUE)Dashboard: http://localhost:8080$(NC)"
	@echo "$(BLUE)API (via oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo "$(BLUE)Database (admin access): localhost:5432$(NC)"
	@echo "$(GREEN)✅ Application containers restarted (database preserved)$(NC)"

containers-start-fast: ## Start containers without building (faster startup)
	@echo "$(GREEN)Starting complete Tarsy container stack (no build)...$(NC)"
	COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml up -d
	@echo "$(BLUE)Dashboard: http://localhost:8080$(NC)"
	@echo "$(BLUE)API (via oauth2-proxy): http://localhost:8080/api$(NC)"
	@echo "$(BLUE)Database (admin access): localhost:5432$(NC)"
	@echo "$(YELLOW)Note: All traffic routed through nginx reverse proxy with oauth2-proxy authentication$(NC)"

containers-stop: ## Stop all running containers
	@echo "$(YELLOW)Stopping containers...$(NC)"
	-COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml down 2>/dev/null || true
	@echo "$(GREEN)✅ Containers stopped$(NC)"

containers-clean: containers-stop ## Stop and remove all containers, networks, and volumes
	@echo "$(YELLOW)Cleaning up containers, networks, and volumes...$(NC)"
	-podman system prune -f 2>/dev/null || true
	@echo "$(GREEN)✅ Container cleanup completed$(NC)"

containers-logs: ## Show logs from all running containers
	@echo "$(GREEN)Container logs:$(NC)"
	-COMPOSE_PROJECT_NAME=tarsy podman-compose logs --tail=50 2>/dev/null || echo "No containers running"

containers-status: ## Show container status
	@echo "$(GREEN)Container status:$(NC)"
	-podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No containers running"

# Testing targets (leverage backend Makefile)
.PHONY: test
test: ## Run all tests (backend: unit+integration+e2e, dashboard)
	@echo "$(GREEN)Running backend tests...$(NC)"
	$(MAKE) -C backend test
	@echo "$(GREEN)Running dashboard tests...$(NC)"
	cd dashboard && npm run test:run
	@echo "$(GREEN)✅ All tests completed$(NC)"

.PHONY: test-backend
test-backend: ## Run backend tests only
	$(MAKE) -C backend test

.PHONY: test-dashboard
test-dashboard: ## Run dashboard tests only
	cd dashboard && npm run test:run 

# Code quality targets (leverage backend Makefile)
.PHONY: lint
lint: ## Run linting for all components
	@echo "$(GREEN)Running backend lint...$(NC)"
	$(MAKE) -C backend lint
	@echo "$(GREEN)Running dashboard lint...$(NC)"
	cd dashboard && npm run lint
	@echo "$(GREEN)✅ All linting completed$(NC)"

.PHONY: lint-fix
lint-fix: ## Auto-fix linting issues
	@echo "$(GREEN)Running backend lint-fix...$(NC)"
	$(MAKE) -C backend lint-fix
	@echo "$(GREEN)Running dashboard lint...$(NC)"
	cd dashboard && npm run lint
	@echo "$(GREEN)✅ Linting fixes applied$(NC)"

# Build targets
.PHONY: build
build: ## Build for production
	@echo "$(GREEN)Building all components...$(NC)"
	cd dashboard && npm run build
	@echo "$(GREEN)✅ Build completed$(NC)"

# Cleanup targets
.PHONY: clean
clean: ## Clean build artifacts and caches
	@echo "$(GREEN)Cleaning all components...$(NC)"
	$(MAKE) -C backend clean
	cd dashboard && rm -rf dist/ node_modules/
	rm -rf node_modules/
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

.PHONY: reset
reset: clean ## Full reset (clean + remove .env files)
	@echo "$(YELLOW)⚠️  This will remove .env files!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo "$(YELLOW)Removing .env files...$(NC)"; \
			rm -f backend/.env; \
			echo "$(GREEN)✅ Full reset completed$(NC)"; \
			;; \
		*) \
			echo "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

# Status and info targets
.PHONY: status
status: ## Show which services are running and project status
	@echo "$(GREEN)TARSy Service Status$(NC)"
	@echo "=========================="
	@echo "Backend (port $(BACKEND_PORT)): $$(if lsof -i:$(BACKEND_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo "Dashboard (port $(DASHBOARD_PORT)): $$(if lsof -i:$(DASHBOARD_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo ""
	$(MAKE) -C backend status

.PHONY: urls
urls: ## Display service URLs and endpoints
	@echo "$(GREEN)TARSy Service URLs$(NC)"
	@echo "======================"
	@echo "$(BLUE)🌍 Frontend Applications:$(NC)"
	@echo "  SRE Dashboard:   http://localhost:$(DASHBOARD_PORT)"
	@echo "    - Manual Alert Submission: http://localhost:$(DASHBOARD_PORT)/submit-alert"
	@echo ""
	@echo "$(BLUE)🔧 Backend Services:$(NC)"
	@echo "  API Server:      http://localhost:$(BACKEND_PORT)"
	@echo "  API Docs:        http://localhost:$(BACKEND_PORT)/docs"
	@echo "  Health Check:    http://localhost:$(BACKEND_PORT)/health"

.PHONY: logs
logs: ## Show recent logs from all services
	$(MAKE) -C backend logs

# Help target
.PHONY: help
help: ## Show this help message
	@echo "$(GREEN)TARSy Development Commands$(NC)"
	@echo "================================="
	@echo ""
	@echo "$(YELLOW)🚀 Quick Start:$(NC)"
	@echo "  make setup        # First time setup"
	@echo "  make dev          # Start all services (direct backend)"
	@echo "  make stop         # Stop all services"
	@echo ""
	@echo "$(YELLOW)🐳 Container Deployment:$(NC)"
	@echo "  make containers-deploy        # Deploy stack (rebuild apps, preserve database)"
	@echo "  make containers-deploy-fresh  # Deploy fresh stack (rebuild everything)"
	@echo "  make containers-stop          # Stop all containers"
	@echo "  make containers-clean         # Remove containers and volumes"
	@echo "  make containers-status        # Show container status"
	@echo ""
	@echo "$(YELLOW)📋 Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)💡 Tip:$(NC) Run 'make urls' to see all service URLs" 