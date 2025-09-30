# Cleanup targets
.PHONY: clean
clean: ## Clean build artifacts and caches
	@echo -e "$(GREEN)Cleaning all components...$(NC)"
	$(MAKE) -C backend clean
	cd dashboard && rm -rf dist/ node_modules/
	rm -rf node_modules/
	@echo -e "$(GREEN)✅ Cleanup completed$(NC)"

.PHONY: reset
reset: clean ## Full reset (clean + remove .env files)
	@echo -e "$(YELLOW)⚠️  This will remove .env files!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo -e "$(YELLOW)Removing .env files...$(NC)"; \
			rm -f backend/.env; \
			echo -e "$(GREEN)✅ Full reset completed$(NC)"; \
			;; \
		*) \
			echo -e "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac
