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
	@echo "  make containers-deploy        # Deploy stack (smart: rebuild apps, preserve database)"
	@echo "  make containers-deploy-fresh  # Deploy fresh stack (rebuild everything)"
	@echo "  make containers-start         # Start containers (quick restart after stop)"
	@echo "  make containers-stop          # Stop all containers"
	@echo "  make containers-db-reset      # Reset database volume (fixes version conflicts)"
	@echo "  make containers-clean         # Remove containers, volumes, and networks"
	@echo "  make sync-backend-deps        # Sync backend dependencies (update uv.lock)"
	@echo ""
	@echo "$(YELLOW)📋 Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)💡 Tip:$(NC) Run 'make urls' to see all service URLs" 