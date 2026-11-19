
import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# --------------------------------------------------
# 1. LOAD DATABASE CONFIGURATION
# --------------------------------------------------

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Check your .env file."
    )


# --------------------------------------------------
# 2. VALIDATE DATABASE CONFIGURATION
# --------------------------------------------------

database_url = make_url(DATABASE_URL)

if database_url.get_backend_name() != "postgresql":
    raise ValueError("Only PostgreSQL is supported.")

if database_url.get_driver_name() != "psycopg":
    raise ValueError("Use the Psycopg 3 driver.")


# --------------------------------------------------
# 3. CREATE DATABASE ENGINE
# --------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={
        "connect_timeout": 5
    }
)


# --------------------------------------------------
# 4. DECLARATIVE BASE
# --------------------------------------------------

class Base(DeclarativeBase):
    """
    Parent class for all SQLAlchemy database models.
    """

    pass


# --------------------------------------------------
# 5. DATABASE SESSION FACTORY
# --------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False
)


# --------------------------------------------------
# 6. DATABASE DEPENDENCY
# --------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    Provides a database session to a FastAPI request.
    Closes the session automatically afterward.
    """

    with SessionLocal() as db:
        yield db


# --------------------------------------------------
# 7. INITIALIZE DATABASE TABLES
# --------------------------------------------------

def init_db() -> None:
    """
    Creates all registered database tables.

    Model modules must be imported before calling
    this function.
    """

    Base.metadata.create_all(bind=engine)
