from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.database import Base
from models.user import User
from routes.admin import (
    UserStatusUpdate,
    list_users,
    update_user_status,
)
from utils.security import hash_password


@pytest.fixture
def admin_context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin-routes.sqlite'}")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    admin = User(
        full_name="Administrator",
        email="admin@example.com",
        hashed_password=hash_password("valid-admin-password-123"),
        role="admin",
        is_active=True,
    )
    staff = User(
        full_name="Staff Member",
        email="staff@example.com",
        hashed_password=hash_password("valid-staff-password-123"),
        role="staff",
        is_active=True,
    )
    db.add_all([admin, staff])
    db.commit()
    db.refresh(admin)
    db.refresh(staff)
    try:
        yield db, admin, staff
    finally:
        db.close()
        engine.dispose()


def test_admin_user_listing_is_paginated_and_excludes_password_hash(admin_context):
    db, admin, _ = admin_context

    result = list_users(page=1, page_size=1, db=db, admin=admin)

    assert result.total == 2
    assert result.page == 1
    assert result.page_size == 1
    assert result.total_pages == 2
    assert len(result.items) == 1
    assert "hashed_password" not in result.items[0].model_dump()
    assert isinstance(result.items[0].created_at, datetime)


def test_admin_can_deactivate_staff_but_cannot_deactivate_self(admin_context):
    db, admin, staff = admin_context

    result = update_user_status(
        user_id=staff.id,
        payload=UserStatusUpdate(is_active=False),
        db=db,
        admin=admin,
    )
    assert result.is_active is False
    assert db.get(User, staff.id).is_active is False

    with pytest.raises(HTTPException) as error:
        update_user_status(
            user_id=admin.id,
            payload=UserStatusUpdate(is_active=False),
            db=db,
            admin=admin,
        )
    assert error.value.status_code == 400
    assert db.get(User, admin.id).is_active is True


def test_admin_status_update_rejects_role_mutation_and_missing_users(admin_context):
    db, admin, staff = admin_context

    with pytest.raises(ValidationError):
        UserStatusUpdate(is_active=False, role="admin")

    with pytest.raises(HTTPException) as error:
        update_user_status(
            user_id=99999,
            payload=UserStatusUpdate(is_active=False),
            db=db,
            admin=admin,
        )
    assert error.value.status_code == 404
    assert db.get(User, staff.id).role == "staff"
