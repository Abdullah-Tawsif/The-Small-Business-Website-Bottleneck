"""Alembic environment with an explicit target safety guard."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from database.migration_safety import migration_database_url

# Validate the shell-provided target before importing application modules;
# database.database loads .env for normal app use, but migrations must not
# silently inherit a target from that file.
DATABASE_URL = migration_database_url()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from database.database import Base  # noqa: E402
from models import ai_session, lead, package, user  # noqa: E402, F401
from database.legacy_adoption import verify_legacy_schema  # noqa: E402

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Baseline stamping adopts an existing schema; never stamp a partial or
        # unrelated database. Fresh databases use `upgrade`, which creates it.
        if getattr(config.cmd_opts, "cmd", None) == "stamp":
            verify_legacy_schema(connection.engine)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
