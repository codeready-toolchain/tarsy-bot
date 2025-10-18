# Testing targets (leverage backend Makefile)
.PHONY: test
test: ## Run all tests (backend: unit+integration+e2e, dashboard build+tests)
	@echo -e "$(GREEN)Running backend tests...$(NC)"
	$(MAKE) -C backend test
	@echo -e "$(GREEN)Building dashboard (TypeScript check)...$(NC)"
	cd dashboard && npm run build
	@echo -e "$(GREEN)Running dashboard tests...$(NC)"
	cd dashboard && npm run test:run
	@echo -e "$(GREEN)✅ All tests completed$(NC)"

.PHONY: test-backend
test-backend: ## Run backend tests only
	$(MAKE) -C backend test

.PHONY: test-dashboard
test-dashboard: ## Run dashboard tests only
	cd dashboard && npm run test:run

.PHONY: test-dashboard-build
test-dashboard-build: ## Run dashboard TypeScript build check (for CI)
	@echo -e "$(GREEN)Building dashboard (TypeScript check)...$(NC)"
	cd dashboard && npm run build
	@echo -e "$(GREEN)✅ Dashboard build completed$(NC)"

.PHONY: test-dashboard-all
test-dashboard-all: test-dashboard-build test-dashboard ## Run dashboard build check and tests
	@echo -e "$(GREEN)✅ All dashboard checks completed$(NC)" 