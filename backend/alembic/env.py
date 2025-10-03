from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import TARSy settings and models
from tarsy.config.settings import get_settings
from sqlmodel import SQLModel

# Import all database models for autogenerate support
from tarsy.models.db_models import *  # noqa: F403, F401
from tarsy.models.unified_interactions import *  # noqa: F403, F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set database URL from TARSy settings (only if not already set programmatically)
# When run via migrations.py, the URL is already set in config
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    if settings.history_enabled and settings.database_url:
        config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata from SQLModel for autogenerate support
target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    """Run migrations by connecting to the database and executing SQL directly.

    This is the standard approach for TARSy - migrations are applied
    automatically on application startup.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Enable batch mode for SQLite to handle ALTER TABLE limitations
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


# Run migrations online (TARSy only uses online migrations)
run_migrations_online()
