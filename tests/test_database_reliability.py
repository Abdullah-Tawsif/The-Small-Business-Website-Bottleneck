from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.database import Base, create_database_engine
from models.ai_session import AISession
from models.lead import Lead  # noqa: F401
from models.package import Package  # noqa: F401
from models.user import User
from services.auth_service import register_user


def test_sqlite_engine_enforces_foreign_keys(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'foreign-keys.sqlite'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(AISession(id=uuid4(), lead_id=987654))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    finally:
        engine.dispose()


def test_concurrent_registration_creates_at_most_one_account(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'concurrent-auth.sqlite'}")
    Base.metadata.create_all(engine)

    def register():
        with Session(engine, expire_on_commit=False) as db:
            try:
                user = register_user(
                    db,
                    full_name="Concurrent User",
                    email="race-condition@example.invalid",
                    password="concurrency-test-password-123",
                )
                return ("created", user.id)
            except ValueError as error:
                return ("duplicate", str(error))

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: register(), range(2)))
        assert sorted(result[0] for result in results) == ["created", "duplicate"]
        with Session(engine) as db:
            count = db.scalar(
                select(func.count()).select_from(User).where(
                    User.email == "race-condition@example.invalid"
                )
            )
        assert count == 1
    finally:
        engine.dispose()
