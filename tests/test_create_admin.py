import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from create_admin import create_admin_account
from database.database import Base
from models.user import User
from utils.security import verify_password


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'create-admin.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def test_initial_admin_creation_hashes_password_and_normalizes_account(db_session):
    admin = create_admin_account(
        db_session,
        full_name="  Admin User  ",
        email="  Admin@Example.com  ",
        password="valid-initial-admin-password-123",
    )

    assert admin.full_name == "Admin User"
    assert admin.email == "admin@example.com"
    assert admin.role == "admin"
    assert admin.is_active is True
    assert verify_password(
        "valid-initial-admin-password-123",
        admin.hashed_password,
    )


def test_initial_admin_creation_never_promotes_existing_staff(db_session):
    staff = User(
        full_name="Existing Staff",
        email="person@example.com",
        hashed_password="existing-hash",
        role="staff",
        is_active=False,
    )
    db_session.add(staff)
    db_session.commit()

    with pytest.raises(ValueError, match="No account was modified"):
        create_admin_account(
            db_session,
            full_name="New Admin",
            email=" PERSON@example.com ",
            password="valid-initial-admin-password-123",
        )

    db_session.refresh(staff)
    assert staff.role == "staff"
    assert staff.is_active is False
    assert staff.hashed_password == "existing-hash"


@pytest.mark.parametrize("full_name", ["", "a" * 101])
def test_initial_admin_creation_rejects_invalid_names(db_session, full_name):
    with pytest.raises(ValueError, match="Invalid full name"):
        create_admin_account(
            db_session,
            full_name=full_name,
            email="admin@example.com",
            password="valid-initial-admin-password-123",
        )


def test_main_reports_unmigrated_database_without_traceback(monkeypatch, capsys):
    import create_admin

    def reject_unmigrated_database():
        raise RuntimeError(
            "Database schema is not initialized. Run `alembic upgrade head` first."
        )

    monkeypatch.setattr(create_admin, "verify_schema", reject_unmigrated_database)

    assert create_admin.main() == 1
    output = capsys.readouterr().out
    assert "Database schema is not ready" in output
    assert "alembic upgrade head" in output
    assert "Traceback" not in output
