# Tarsy Backend - Makefile
# ==========================

# Default target
.DEFAULT_GOAL := help

# Variables
UV := uv
TEST_DIR := tests
APP_DIR := app
PYTEST := TESTING=true $(UV) run python -m pytest
E2E_TEST_COUNT := 20

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
.PHONY: clean-test-db
clean-test-db: ## Clean test database to ensure fresh state
	@echo "$(GREEN)Cleaning test database...$(NC)"
	@rm -f test.db test.db-shm test.db-wal
	@rm -rf /tmp/tarsy_e2e_test_* 2>/dev/null || true
	@find /tmp -name "e2e_test_*.db*" -delete 2>/dev/null || true
	@echo "$(GREEN)Test database cleaned$(NC)"

.PHONY: test
test: check-test-deps test-unit clean-test-db test-integration clean-test-db test-e2e ## Run all tests (unit + integration + e2e) with proper isolation

.PHONY: test-unit
test-unit: check-test-deps ## Run unit tests only
	@echo "$(GREEN)Running unit tests...$(NC)"
	TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/unit/ -v --tb=short

.PHONY: test-integration
test-integration: check-test-deps clean-test-db ## Run integration tests only (with clean database)
	@echo "$(GREEN)Running integration tests...$(NC)"
	TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/integration/ -v --tb=short

.PHONY: test-e2e
test-e2e: check-test-deps clean-test-db ## Run end-to-end tests only (one by one for isolation, with clean database)
	@echo "$(GREEN)Running end-to-end tests sequentially (grouped by function)...$(NC)"
	@echo ""
	@echo "$(GREEN)═══ GROUP 1: Core Functionality ═══$(NC)"
	@echo "$(YELLOW)Running 1st of $(E2E_TEST_COUNT) E2E tests (API operations)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_api_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 2nd of $(E2E_TEST_COUNT) E2E tests (runbook integration)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_runbooks_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 3rd of $(E2E_TEST_COUNT) E2E tests (stage failure detection)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_stage_failure_detection_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo ""
	@echo "$(GREEN)═══ GROUP 2: Iteration Strategies & Basic Parallel ═══$(NC)"
	@echo "$(YELLOW)Running 4th of $(E2E_TEST_COUNT) E2E tests (native thinking)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_native_thinking_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 5th of $(E2E_TEST_COUNT) E2E tests (parallel multi-agent)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_parallel_multi_agent_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 6th of $(E2E_TEST_COUNT) E2E tests (parallel replica)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_parallel_replica_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 7th of $(E2E_TEST_COUNT) E2E tests (parallel then regular)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_parallel_then_regular_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo ""
	@echo "$(GREEN)═══ GROUP 3: Pause/Resume/Cancel/Conclude (Single & Parallel) ═══$(NC)"
	@echo "$(YELLOW)Running 8th of $(E2E_TEST_COUNT) E2E tests (pause/resume - single agent)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_pause_resume_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 9th of $(E2E_TEST_COUNT) E2E tests (native thinking pause/resume)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_native_thinking_pause_resume_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 10th of $(E2E_TEST_COUNT) E2E tests (parallel pause/resume)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_pause_resume_parallel_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 11th of $(E2E_TEST_COUNT) E2E tests (forced conclusion parallel)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_forced_conclusion_parallel_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 12th of $(E2E_TEST_COUNT) E2E tests (cancel session during parallel)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_cancel_session_parallel_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 13th of $(E2E_TEST_COUNT) E2E tests (cancel agent - policy any)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_cancel_parallel_agent_e2e.py::TestCancelParallelAgentE2E::test_cancel_paused_agent_with_policy_any_triggers_continuation -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 14th of $(E2E_TEST_COUNT) E2E tests (cancel agent - stays paused)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_cancel_parallel_agent_e2e.py::TestCancelParallelAgentE2E::test_cancel_one_paused_agent_keeps_session_paused -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 15th of $(E2E_TEST_COUNT) E2E tests (cancel agent - three agents)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_cancel_parallel_agent_e2e.py::TestCancelParallelAgentE2E::test_cancel_only_paused_agent_among_three_agents_session_completes -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo ""
	@echo "$(GREEN)═══ GROUP 4: Failure Handling ═══$(NC)"
	@echo "$(YELLOW)Running 16th of $(E2E_TEST_COUNT) E2E tests (single-agent LangChain failure)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_single_agent_llm_failure_e2e.py::TestSingleAgentLangChainFailureE2E -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 17th of $(E2E_TEST_COUNT) E2E tests (single-agent Gemini failure)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_single_agent_llm_failure_e2e.py::TestSingleAgentGeminiNativeThinkingFailureE2E -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 18th of $(E2E_TEST_COUNT) E2E tests (single-agent intermittent failure)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_single_agent_llm_failure_e2e.py::TestSingleAgentIntermittentFailureE2E -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo "$(YELLOW)Running 19th of $(E2E_TEST_COUNT) E2E tests (parallel LLM failure)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_parallel_llm_failure_e2e.py -v --tb=short -m e2e || exit 1
	@$(MAKE) clean-test-db
	@echo ""
	@echo "$(GREEN)═══ GROUP 5: Concurrency & Scale ═══$(NC)"
	@echo "$(YELLOW)Running 20th of $(E2E_TEST_COUNT) E2E tests (concurrent sessions)...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/e2e/test_concurrent_alert_sessions.py -v --tb=short -m e2e || exit 1
	@echo ""
	@echo "$(GREEN)All E2E tests completed successfully!$(NC)"

.PHONY: test-coverage
test-coverage: check-test-deps clean-test-db ## Run unit and integration tests with coverage report (no e2e-tests for stability, with clean database)
	@echo "$(GREEN)Running unit and integration tests with coverage...$(NC)"
	@TESTING=true .venv/bin/python -m pytest $(TEST_DIR)/unit/ $(TEST_DIR)/integration/ --cov=tarsy --cov-report=html --cov-report=xml --cov-report=term-missing --tb=short
	@echo "$(GREEN)All tests with coverage completed!$(NC)"

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
	@if ! .venv/bin/python -c "import pytest, xdist, respx" 2>/dev/null; then \
		echo "$(YELLOW)Test dependencies not found. Installing...$(NC)"; \
		$(UV) sync --extra test; \
	fi

.PHONY: dev
dev: check-venv ## Start development server with auto-reload
	@echo "$(GREEN)Starting development server...$(NC)"
	.venv/bin/uvicorn tarsy.main:app --reload --port 8000 --log-config uvicorn_logging_config.json --log-level info

.PHONY: dev-debug
dev-debug: check-venv ## Start development server with debug logging
	@echo "$(GREEN)Starting development server (debug mode)...$(NC)"
	LOG_LEVEL=DEBUG .venv/bin/uvicorn tarsy.main:app --reload --port 8000 --log-config uvicorn_logging_config.json --log-level debug

.PHONY: run
run: check-venv ## Start development server with manual venv activation
	@echo "$(GREEN)Starting development server (manual venv)...$(NC)"
	.venv/bin/uvicorn tarsy.main:app --reload --host 0.0.0.0 --port 8000 --log-config uvicorn_logging_config.json

.PHONY: run-prod
run-prod: check-venv ## Start production server (no reload, optimized for production)
	@echo "$(GREEN)Starting production server...$(NC)"
	.venv/bin/uvicorn tarsy.main:app --host 0.0.0.0 --port 8000 --log-config uvicorn_logging_config.json

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

# JWT Authentication
.PHONY: generate-jwt-keys
generate-jwt-keys: ## Generate RSA key pair for JWT signing/validation
	@echo "$(GREEN)Generating JWT RSA key pair...$(NC)"
	@mkdir -p ../config/keys
	@openssl genrsa -out ../config/keys/jwt_private_key.pem 2048
	@openssl rsa -in ../config/keys/jwt_private_key.pem -pubout -out ../config/keys/jwt_public_key.pem
	@chmod 600 ../config/keys/jwt_private_key.pem  # Secure private key
	@chmod 644 ../config/keys/jwt_public_key.pem   # Public key can be readable
	@echo "$(GREEN)JWT keys generated successfully!$(NC)"
	@echo "$(YELLOW)Private key: config/keys/jwt_private_key.pem (keep secure!)$(NC)"
	@echo "$(YELLOW)Public key: config/keys/jwt_public_key.pem$(NC)"

.PHONY: generate-api-token
generate-api-token: ## Generate JWT token for API access (365-day expiration, subject: monitoring-system, issuer: http://localhost:8000)
	@echo "$(GREEN)Generating JWT API token...$(NC)"
	@$(UV) run python3 generate_token.py 365

.PHONY: generate-api-token-exp
generate-api-token-exp: ## Generate JWT token with custom expiration (Usage: make generate-api-token-exp DAYS=365 [SUBJECT=monitoring-system] [ISSUER=http://localhost:8000] [KEY_PATH=/custom/path.pem])
	@if [ -z "$(DAYS)" ]; then \
		echo "$(RED)Usage: make generate-api-token-exp DAYS=<number> [SUBJECT=<subject>] [ISSUER=<issuer>] [KEY_PATH=<path>]$(NC)"; \
		echo "$(YELLOW)Example: make generate-api-token-exp DAYS=365 SUBJECT=prometheus ISSUER=https://api.production.com$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Generating JWT API token ($(DAYS) days expiration)...$(NC)"
	@if [ -n "$(SUBJECT)" ] || [ -n "$(ISSUER)" ] || [ -n "$(KEY_PATH)" ]; then \
		$(UV) run python3 generate_token.py $(DAYS) \
			$$(if [ -n "$(KEY_PATH)" ]; then echo "$(KEY_PATH)"; else echo "$$(cd .. && pwd)/config/keys/jwt_private_key.pem"; fi) \
			$$(if [ -n "$(SUBJECT)" ]; then echo "$(SUBJECT)"; else echo "monitoring-system"; fi) \
			$$(if [ -n "$(ISSUER)" ]; then echo "$(ISSUER)"; else echo "http://localhost:8000"; fi); \
	else \
		$(UV) run python3 generate_token.py $(DAYS); \
	fi

.PHONY: verify-jwt-setup
verify-jwt-setup: ## Verify JWT authentication setup
	@echo "$(GREEN)Verifying JWT authentication setup...$(NC)"
	@if [ -f ../config/keys/jwt_private_key.pem ] && [ -f ../config/keys/jwt_public_key.pem ]; then \
		echo "$(GREEN)✓ JWT keys found$(NC)"; \
		echo "Private key: config/keys/jwt_private_key.pem"; \
		echo "Public key: config/keys/jwt_public_key.pem"; \
	else \
		echo "$(RED)✗ JWT keys not found$(NC)"; \
		echo "Run 'make generate-jwt-keys' to create them"; \
		exit 1; \
	fi
	@echo "$(GREEN)JWT authentication setup verified!$(NC)"

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