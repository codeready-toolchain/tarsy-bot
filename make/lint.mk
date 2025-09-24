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