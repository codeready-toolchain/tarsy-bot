# Tarsy-bot - Development Makefile
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
ALERT_UI_PORT := 3001
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
	@echo "$(GREEN)🚀 Setting up Tarsy-bot development environment...$(NC)"
	@echo "$(BLUE)Setting up backend...$(NC)"
	$(MAKE) -C backend install
	@if [ ! -f backend/.env ]; then \
		echo "$(YELLOW)Creating backend/.env from template...$(NC)"; \
		cp backend/env.template backend/.env; \
		echo "$(YELLOW)⚠️  IMPORTANT: Edit backend/.env with your API keys!$(NC)"; \
	else \
		echo "$(GREEN)✓ backend/.env already exists - keeping your configuration$(NC)"; \
	fi
	@echo "$(BLUE)Setting up alert dev UI...$(NC)"
	cd alert-dev-ui && npm install
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
dev: ## Start all services for development
	@echo "$(GREEN)🚀 Starting all services...$(NC)"
	@echo "$(BLUE)Backend will run on: http://localhost:$(BACKEND_PORT)$(NC)"
	@echo "$(BLUE)Alert Dev UI will run on: http://localhost:$(ALERT_UI_PORT)$(NC)"
	@echo "$(BLUE)Dashboard will run on: http://localhost:$(DASHBOARD_PORT)$(NC)"
	@echo ""
	@trap 'make stop' INT; \
	( \
		echo "$(YELLOW)Starting backend...$(NC)" && \
		(cd backend && make dev) & \
		echo "$(YELLOW)Starting alert dev UI...$(NC)" && \
		(cd alert-dev-ui && PORT=$(ALERT_UI_PORT) npm start) & \
		echo "$(YELLOW)Starting dashboard...$(NC)" && \
		(cd dashboard && npm run dev) & \
		wait \
	)

# Individual service targets
.PHONY: backend
backend: ## Start backend only
	@echo "$(GREEN)Starting backend on http://localhost:$(BACKEND_PORT)$(NC)"
	$(MAKE) -C backend dev

.PHONY: alert-ui  
alert-ui: ## Start alert dev UI only
	@echo "$(GREEN)Starting alert dev UI on http://localhost:$(ALERT_UI_PORT)$(NC)"
	cd alert-dev-ui && PORT=$(ALERT_UI_PORT) npm start

.PHONY: dashboard
dashboard: ## Start dashboard only
	@echo "$(GREEN)Starting dashboard on http://localhost:$(DASHBOARD_PORT)$(NC)"
	cd dashboard && npm run dev

# Stop services
.PHONY: stop
stop: ## Stop all running services
	@echo "$(YELLOW)Stopping all services...$(NC)"
	$(MAKE) -C backend stop
	@lsof -ti:$(ALERT_UI_PORT) | xargs -r kill -9 2>/dev/null || true
	@lsof -ti:$(DASHBOARD_PORT) | xargs -r kill -9 2>/dev/null || true
	@echo "$(GREEN)✅ All services stopped$(NC)"

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
	cd alert-dev-ui && npm run build
	cd dashboard && npm run build
	@echo "$(GREEN)✅ Build completed$(NC)"

# Cleanup targets
.PHONY: clean
clean: ## Clean build artifacts and caches
	@echo "$(GREEN)Cleaning all components...$(NC)"
	$(MAKE) -C backend clean
	cd alert-dev-ui && rm -rf build/ node_modules/
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
	@echo "$(GREEN)Tarsy-bot Service Status$(NC)"
	@echo "=========================="
	@echo "Backend (port $(BACKEND_PORT)): $$(if lsof -i:$(BACKEND_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo "Alert UI (port $(ALERT_UI_PORT)): $$(if lsof -i:$(ALERT_UI_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo "Dashboard (port $(DASHBOARD_PORT)): $$(if lsof -i:$(DASHBOARD_PORT) >/dev/null 2>&1; then echo '$(GREEN)Running$(NC)'; else echo '$(RED)Stopped$(NC)'; fi)"
	@echo ""
	$(MAKE) -C backend status

.PHONY: urls
urls: ## Display service URLs and endpoints
	@echo "$(GREEN)Tarsy-bot Service URLs$(NC)"
	@echo "======================"
	@echo "$(BLUE)🌍 Frontend Applications:$(NC)"
	@echo "  Alert Dev UI:    http://localhost:$(ALERT_UI_PORT)"
	@echo "  SRE Dashboard:   http://localhost:$(DASHBOARD_PORT)"
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
	@echo "$(GREEN)Tarsy-bot Development Commands$(NC)"
	@echo "================================="
	@echo ""
	@echo "$(YELLOW)🚀 Quick Start:$(NC)"
	@echo "  make setup     # First time setup"
	@echo "  make dev       # Start all services"
	@echo "  make stop      # Stop all services"
	@echo ""
	@echo "$(YELLOW)📋 Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)💡 Tip:$(NC) Run 'make urls' to see all service URLs" 