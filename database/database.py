
"""SQLAlchemy database configuration and initialization.

SQLite is the zero-configuration local default.
PostgreSQL is supported for production deployments.
"""

from collections.abc import Generator
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from config.settings import get_settings


def configured_database_url() -> str:
    """Return the validated database URL from the shared settings source."""
    settings = get_settings()
    if settings.database_url:
        from sqlalchemy.engine import make_url

        try:
            parsed = make_url(settings.database_url)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("DATABASE_URL is invalid.") from exc
        if settings.environment.lower() == "production" and (
            parsed.get_backend_name() != "postgresql"
            or not parsed.host
            or not parsed.database
        ):
            raise RuntimeError(
                "Production DATABASE_URL must identify a PostgreSQL host and database."
            )
        if parsed.get_backend_name() == "postgresql" and parsed.drivername == "postgresql":
            parsed = parsed.set(drivername="postgresql+psycopg")
        return parsed.render_as_string(hide_password=False)
    if settings.environment.lower() == "production":
        raise RuntimeError("DATABASE_URL is required in production.")
    return "sqlite:///./agencyforge-dev.sqlite"

def create_database_engine(database_url: str):
    """Create an engine with SQLite foreign keys enabled for every connection."""
    from sqlalchemy.engine import make_url

    parsed_url = make_url(database_url)
    if (
        parsed_url.get_backend_name() == "postgresql"
        and parsed_url.drivername == "postgresql"
    ):
        parsed_url = parsed_url.set(drivername="postgresql+psycopg")
    database_url = parsed_url.render_as_string(hide_password=False)
    is_sqlite = parsed_url.get_backend_name() == "sqlite"
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


DATABASE_URL = configured_database_url()
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
