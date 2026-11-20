
"""SQLAlchemy database configuration and initialization.

SQLite is the zero-configuration local default.
PostgreSQL is supported for production deployments.
"""

import os
from collections.abc import Generator
from pathlib import Path

from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./agencyforge-dev.sqlite",
)

def create_database_engine(database_url: str):
    """Create an engine with SQLite foreign keys enabled for every connection."""
    is_sqlite = database_url.startswith("sqlite")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=(
            {"check_same_thread": False}
            if is_sqlite
            else {"connect_timeout": 5}
        ),
    )
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = create_database_engine(DATABASE_URL)


class Base(DeclarativeBase):
    """Base class shared by all SQLAlchemy models."""

    pass


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide a database session to FastAPI endpoints."""

    with SessionLocal() as db:
        yield db


def verify_schema() -> None:
    """Require a current schema; ordinary startup must never mutate it."""

    from models.ai_session import AISession  # noqa: F401
    from models.lead import Lead  # noqa: F401
    from models.package import Package  # noqa: F401
    from models.user import User  # noqa: F401

    inspector = inspect(engine)
    missing_tables = sorted(
        set(Base.metadata.tables) - set(inspector.get_table_names())
    )
    if missing_tables or not inspector.has_table("alembic_version"):
        raise RuntimeError(
            "Database schema is not initialized. Run `alembic upgrade head` first."
        )

    scripts = ScriptDirectory(
        str(Path(__file__).resolve().parents[1] / "migrations")
    )
    expected_revision = scripts.get_current_head()
    with engine.connect() as connection:
        current_revision = connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )
    if current_revision != expected_revision:
        raise RuntimeError(
            "Database schema is not at the latest migration. Run `alembic upgrade head`."
        )
