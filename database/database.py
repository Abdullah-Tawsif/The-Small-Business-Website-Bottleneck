
"""SQLAlchemy database configuration and initialization.

SQLite is the zero-configuration local default.
PostgreSQL is supported for production deployments.
"""

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./agencyforge.db",
)

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {"connect_timeout": 5}
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)


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


def init_db() -> None:
    """
    Import all application models before creating database tables.

    Imports are intentionally local to avoid circular imports because
    each model imports Base from this module.
    """

    from models.user import User  # noqa: F401
    from models.package import Package  # noqa: F401
    from models.lead import Lead  # noqa: F401
    from models.ai_session import AISession  # noqa: F401

    Base.metadata.create_all(bind=engine)
