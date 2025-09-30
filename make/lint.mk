# Code quality targets (leverage backend Makefile)
.PHONY: lint
lint: ## Run linting for all components
	@echo -e "$(GREEN)Running backend lint...$(NC)"
	$(MAKE) -C backend lint
	@echo -e "$(GREEN)Running dashboard lint...$(NC)"
	cd dashboard && npm run lint
	@echo -e "$(GREEN)✅ All linting completed$(NC)"

.PHONY: lint-fix
lint-fix: ## Auto-fix linting issues
	@echo -e "$(GREEN)Running backend lint-fix...$(NC)"
	$(MAKE) -C backend lint-fix
	@echo -e "$(GREEN)Running dashboard lint...$(NC)"
	cd dashboard && npm run lint
	@echo -e "$(GREEN)✅ Linting fixes applied$(NC)"