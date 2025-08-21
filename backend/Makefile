# Tarsy Backend - Makefile
# ==========================

# Default target
.DEFAULT_GOAL := help

# Variables
UV := uv
TEST_DIR := tests
APP_DIR := app
PYTEST := TESTING=true $(UV) run python -m pytest

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Help target
.PHONY: help
help: ## Show this help message
	@echo "$(GREEN)Tarsy Backend - Available Commands$(NC)"
	@echo "==================================="
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# Setup and Installation
.PHONY: install
install: ## Install all dependencies (production + development + test)
	@echo "$(GREEN)Installing dependencies...$(NC)"
	$(UV) sync
	$(UV) sync --extra dev --extra test

.PHONY: install-prod
install-prod: ## Install production dependencies only
	@echo "$(GREEN)Installing production dependencies...$(NC)"
	$(UV) sync

.PHONY: install-dev
install-dev: ## Install development dependencies (includes test)
	@echo "$(GREEN)Installing development dependencies...$(NC)"
	$(UV) sync --extra dev --extra test

# Testing
.PHONY: test
test: check-test-deps ## Run all tests (unit + integration + e2e) with proper isolation
	@echo "$(GREEN)Running all tests with proper isolation...$(NC)"
	@echo "$(YELLOW)Running unit and integration tests...$(NC)"
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/unit/ $(TEST_DIR)/integration/ -v --tb=short'
	@echo "$(YELLOW)Running e2e tests in isolated session...$(NC)"  
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/e2e/ -v --tb=short -m e2e'
	@echo "$(GREEN)All tests completed with proper isolation!$(NC)"

.PHONY: test-unit
test-unit: check-test-deps ## Run unit tests only
	@echo "$(GREEN)Running unit tests...$(NC)"
	bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/unit/ -v --tb=short'

.PHONY: test-integration
test-integration: check-test-deps ## Run integration tests only
	@echo "$(GREEN)Running integration tests...$(NC)"
	bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/integration/ -v --tb=short'

.PHONY: test-e2e
test-e2e: check-test-deps ## Run end-to-end tests only
	@echo "$(GREEN)Running end-to-end tests...$(NC)"
	bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/e2e/ -v --tb=short -m e2e'

.PHONY: test-verbose
test-verbose: check-test-deps ## Run all tests with verbose output (isolated sessions for stability)
	@echo "$(GREEN)Running all tests with verbose output and proper isolation...$(NC)"
	@echo "$(YELLOW)Running unit and integration tests (verbose)...$(NC)"
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/unit/ $(TEST_DIR)/integration/ -v --tb=short'
	@echo "$(YELLOW)Running e2e tests in isolated session (verbose)...$(NC)"  
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/e2e/ -v --tb=short -m e2e'
	@echo "$(GREEN)All verbose tests completed!$(NC)"

.PHONY: test-coverage
test-coverage: check-test-deps ## Run unit and integration tests with coverage report (no e2e-tests for stability)
	@echo "$(GREEN)Running unit and integration tests with coverage...$(NC)"
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/unit/ $(TEST_DIR)/integration/ --cov=tarsy --cov-report=html --cov-report=term-missing --tb=short'
	@echo "$(GREEN)All tests with coverage completed!$(NC)"

.PHONY: test-quick
test-quick: check-test-deps ## Run tests in parallel for faster execution (isolated sessions for stability)
	@echo "$(GREEN)Running tests in parallel with proper isolation...$(NC)"
	@echo "$(YELLOW)Running unit and integration tests in parallel...$(NC)"
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/unit/ $(TEST_DIR)/integration/ -n auto -v --tb=short'
	@echo "$(YELLOW)Running e2e tests in isolated session...$(NC)"  
	@bash -c 'source .venv/bin/activate && TESTING=true python -m pytest $(TEST_DIR)/e2e/ -v --tb=short -m e2e'
	@echo "$(GREEN)All parallel tests completed!$(NC)"

# Code Quality
.PHONY: lint
lint: ## Run linting checks with ruff
	@echo "$(GREEN)Running linting checks...$(NC)"
	$(UV) run ruff check $(APP_DIR) $(TEST_DIR)

.PHONY: lint-fix
lint-fix: ## Run linting checks and auto-fix issues
	@echo "$(GREEN)Running linting with auto-fix...$(NC)"
	$(UV) run ruff check --fix $(APP_DIR) $(TEST_DIR)

.PHONY: format
format: ## Format code with black
	@echo "$(GREEN)Formatting code...$(NC)"
	$(UV) run black $(APP_DIR) $(TEST_DIR)

.PHONY: format-check
format-check: ## Check code formatting without making changes
	@echo "$(GREEN)Checking code formatting...$(NC)"
	$(UV) run black --check $(APP_DIR) $(TEST_DIR)

.PHONY: type-check
type-check: ## Run type checking with mypy
	@echo "$(GREEN)Running type checks...$(NC)"
	$(UV) run mypy $(APP_DIR)

.PHONY: quality
quality: lint format-check type-check ## Run all code quality checks
	@echo "$(GREEN)All code quality checks completed!$(NC)"

.PHONY: fix
fix: lint-fix format ## Auto-fix linting issues and format code
	@echo "$(GREEN)Code fixes and formatting applied!$(NC)"

# Development Server
.PHONY: check-venv
check-venv: ## Check if virtual environment exists and create if needed
	@if [ ! -f .venv/bin/uvicorn ]; then \
		echo "$(YELLOW)Virtual environment not found or incomplete. Running setup...$(NC)"; \
		$(MAKE) install; \
	fi

.PHONY: check-test-deps
check-test-deps: check-venv ## Ensure test dependencies are installed
	@if ! .venv/bin/python -c "import respx" 2>/dev/null; then \
		echo "$(YELLOW)Test dependencies not found. Installing...$(NC)"; \
		$(UV) sync --extra test; \
	fi

.PHONY: dev
dev: check-venv ## Start development server with auto-reload
	@echo "$(GREEN)Starting development server...$(NC)"
	.venv/bin/uvicorn tarsy.main:app --reload --port 8000 --log-level info

.PHONY: dev-debug
dev-debug: check-venv ## Start development server with debug logging
	@echo "$(GREEN)Starting development server (debug mode)...$(NC)"
	.venv/bin/uvicorn tarsy.main:app --reload --port 8000 --log-level debug

.PHONY: run
run: check-venv ## Start development server with manual venv activation
	@echo "$(GREEN)Starting development server (manual venv)...$(NC)"
	.venv/bin/uvicorn tarsy.main:app --reload --port 8000

.PHONY: stop
stop: ## Stop backend server running on port 8000
	@echo "$(GREEN)Stopping backend server...$(NC)"
	@lsof -ti:8000 | xargs -r kill -9 || echo "No process found on port 8000"
	@echo "$(GREEN)Backend server stopped$(NC)"

# Database and Cleanup
.PHONY: clean
clean: ## Clean up generated files and caches
	@echo "$(GREEN)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	rm -rf .mypy_cache/ 2>/dev/null || true
	rm -rf .ruff_cache/ 2>/dev/null || true

.PHONY: clean-db
clean-db: ## Clean up database files (USE WITH CAUTION)
	@echo "$(RED)WARNING: This will delete database files!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo "$(YELLOW)Removing database files...$(NC)"; \
			rm -f history.db history.db-shm history.db-wal; \
			echo "$(GREEN)Database files removed$(NC)"; \
			;; \
		*) \
			echo "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

# Utility targets
.PHONY: check
check: quality test-unit ## Run quality checks and unit tests (fast CI check)
	@echo "$(GREEN)Quick check completed successfully!$(NC)"

.PHONY: ci
ci: quality test ## Run full CI pipeline (quality + all tests)
	@echo "$(GREEN)CI pipeline completed successfully!$(NC)"

.PHONY: logs
logs: ## Show recent application logs
	@echo "$(GREEN)Recent application logs:$(NC)"
	@if [ -f logs/tarsy.log ]; then tail -n 50 logs/tarsy.log; else echo "No application logs found"; fi

.PHONY: logs-llm
logs-llm: ## Show recent LLM communication logs
	@echo "$(GREEN)Recent LLM communication logs:$(NC)"
	@if [ -f logs/llm_communications.log ]; then tail -n 50 logs/llm_communications.log; else echo "No LLM logs found"; fi

.PHONY: status
status: ## Show project status and health
	@echo "$(GREEN)Tarsy Backend Status$(NC)"
	@echo "===================="
	@echo "Python version: $$(python3 --version)"
	@echo "UV version: $$(uv --version)"
	@echo "Dependencies: $$(if [ -f uv.lock ]; then echo 'Locked'; else echo 'Not locked'; fi)"
	@echo "Tests: $$(find $(TEST_DIR)/ -name 'test_*.py' | wc -l) test files"
	@echo "Database: $$(if [ -f history.db ]; then echo 'Present'; else echo 'Not found'; fi)"
	@echo "Logs: $$(if [ -d logs ]; then ls logs/ | wc -l; else echo '0'; fi) log files"

# Export variables for sub-processes
export PYTHONPATH := $(shell pwd):$(PYTHONPATH) 