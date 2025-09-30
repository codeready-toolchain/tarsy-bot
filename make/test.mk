# Testing targets (leverage backend Makefile)
.PHONY: test
test: ## Run all tests (backend: unit+integration+e2e, dashboard)
	@echo -e "$(GREEN)Running backend tests...$(NC)"
	$(MAKE) -C backend test
	@echo -e "$(GREEN)Running dashboard tests...$(NC)"
	cd dashboard && npm run test:run
	@echo -e "$(GREEN)✅ All tests completed$(NC)"

.PHONY: test-backend
test-backend: ## Run backend tests only
	$(MAKE) -C backend test

.PHONY: test-dashboard
test-dashboard: ## Run dashboard tests only
	cd dashboard && npm run test:run 