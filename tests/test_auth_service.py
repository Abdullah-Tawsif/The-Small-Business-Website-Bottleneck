import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.database import Base
from models.user import User
from services.auth_service import authenticate_user, register_user
from utils.security import verify_password


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth-service.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def test_registration_normalizes_email_and_assigns_staff_role(db_session):
    user = register_user(
        db_session,
        full_name="  বাংলা নাম  ",
        email="  Person@Example.com  ",
        password="valid-service-password-123",
    )

    assert user.full_name == "বাংলা নাম"
    assert user.email == "person@example.com"
    assert user.role == "staff"
    assert user.is_active is True
    assert verify_password("valid-service-password-123", user.hashed_password)
    assert user.hashed_password != "valid-service-password-123"


def test_registration_rejects_duplicate_normalized_email(db_session):
    register_user(
        db_session,
        full_name="First Person",
        email="person@example.com",
        password="valid-service-password-123",
    )

    with pytest.raises(ValueError, match="already exists"):
        register_user(
            db_session,
            full_name="Second Person",
            email=" PERSON@example.com ",
            password="another-valid-password-123",
        )

    assert db_session.query(User).count() == 1


def test_authentication_accepts_valid_credentials_and_rejects_invalid_ones(db_session):
    user = register_user(
        db_session,
        full_name="Active Person",
        email="active@example.com",
        password="valid-service-password-123",
    )

    assert authenticate_user(
        db_session,
        email=" ACTIVE@example.com ",
        password="valid-service-password-123",
    ).id == user.id
    assert authenticate_user(
        db_session,
        email="active@example.com",
        password="incorrect-password",
    ) is None
    assert authenticate_user(
        db_session,
        email="missing@example.com",
        password="valid-service-password-123",
    ) is None


def test_authentication_rejects_inactive_accounts(db_session):
    user = register_user(
        db_session,
        full_name="Inactive Person",
        email="inactive@example.com",
        password="valid-service-password-123",
    )
    user.is_active = False
    db_session.commit()

    assert authenticate_user(
        db_session,
        email="inactive@example.com",
        password="valid-service-password-123",
    ) is None
