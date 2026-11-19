"""SQLAlchemy database setup. SQLite is the zero-config local default; PostgreSQL is supported."""
import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agencyforge.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {"connect_timeout": 5}
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

class Base(DeclarativeBase):
    pass

SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db

def init_db() -> None:
    # Import the models whose tables belong to the current application startup.
    from models.user import User  # noqa: F401
    Base.metadata.create_all(bind=engine)
