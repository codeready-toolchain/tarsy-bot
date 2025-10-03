# Database Migration Targets
# Requires Alembic to be installed in backend environment

# Variables
UV := uv

.PHONY: migration migration-manual migration-upgrade migration-downgrade migration-status migration-history

migration:  ## Generate migration from model changes: make migration msg="Your message"
	@if [ -z "$(msg)" ]; then \
		echo "Usage: make migration msg='Add new field to AlertSession'"; \
		echo "Example: make migration msg='Add resolution_notes to AlertSession'"; \
		exit 1; \
	fi
	@echo "Generating migration: $(msg)"
	@cd backend && $(UV) run alembic revision --autogenerate -m "$(msg)"
	@echo ""
	@echo "✓ Migration generated in backend/alembic/versions/"
	@echo "⚠️  IMPORTANT: Review the generated file before committing!"
	@echo ""

migration-manual:  ## Create empty migration for manual changes: make migration-manual msg="Your message"
	@if [ -z "$(msg)" ]; then \
		echo "Usage: make migration-manual msg='Transform alert data'"; \
		echo "Example: make migration-manual msg='Migrate alert_type to new format'"; \
		exit 1; \
	fi
	@echo "Creating manual migration: $(msg)"
	@cd backend && $(UV) run alembic revision -m "$(msg)"
	@echo ""
	@echo "✓ Empty migration created in backend/alembic/versions/"
	@echo "📝 Edit the file to add your upgrade() and downgrade() logic"
	@echo ""

migration-upgrade:  ## Apply all pending migrations
	@echo "Applying pending migrations..."
	@cd backend && $(UV) run alembic upgrade head
	@echo "✓ Migrations applied successfully"

migration-downgrade:  ## Rollback the last migration
	@echo "Rolling back last migration..."
	@cd backend && $(UV) run alembic downgrade -1
	@echo "✓ Rollback complete"

migration-status:  ## Show current database schema version
	@echo "Current database version:"
	@cd backend && $(UV) run alembic current

migration-history:  ## Show migration history
	@echo "Migration history:"
	@cd backend && $(UV) run alembic history --verbose

