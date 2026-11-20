import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from config.settings import get_settings
from database.database import Base
from middleware.auth_middleware import (
    _extract_access_token,
    get_current_admin_user,
    get_current_user,
)
from models.user import User
from utils.security import create_access_token, hash_password


@pytest.fixture
def auth_context(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "isolated-auth-middleware-secret-at-least-32-bytes",
    )
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'auth-middleware.sqlite'}")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    active_admin = User(
        full_name="Active Admin",
        email="admin@example.com",
        hashed_password=hash_password("valid-admin-password-123"),
        role="admin",
        is_active=True,
    )
    active_staff = User(
        full_name="Active Staff",
        email="staff@example.com",
        hashed_password=hash_password("valid-staff-password-123"),
        role="staff",
        is_active=True,
    )
    inactive_admin = User(
        full_name="Inactive Admin",
        email="inactive@example.com",
        hashed_password=hash_password("valid-inactive-password-123"),
        role="admin",
        is_active=False,
    )
    db.add_all([active_admin, active_staff, inactive_admin])
    db.commit()
    for user in (active_admin, active_staff, inactive_admin):
        db.refresh(user)
    try:
        yield db, active_admin, active_staff, inactive_admin
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()


def make_request(*, cookie=None, authorization=None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))
    cookies = []
    if cookie is not None:
        cookies.append(f"{get_settings().access_token_cookie_name}={cookie}")
    if cookies:
        headers.append((b"cookie", "; ".join(cookies).encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/protected",
            "headers": headers,
            "client": ("127.0.0.1", 1),
        }
    )


def test_cookie_and_bearer_token_extraction(auth_context):
    _, admin, _, _ = auth_context
    token = create_access_token(admin.id, "admin")

    assert _extract_access_token(make_request(cookie=token)) == token
    assert _extract_access_token(
        make_request(authorization=f"Bearer {token}")
    ) == token


def test_conflicting_credentials_are_rejected(auth_context):
    _, admin, staff, _ = auth_context
    admin_token = create_access_token(admin.id, "admin")
    staff_token = create_access_token(staff.id, "staff")

    with pytest.raises(HTTPException) as error:
        _extract_access_token(
            make_request(
                cookie=admin_token,
                authorization=f"Bearer {staff_token}",
            )
        )

    assert error.value.status_code == 401


def test_database_role_overrides_token_role_for_admin_access(auth_context):
    db, admin, staff, _ = auth_context
    admin_token_with_staff_claim = create_access_token(admin.id, "staff")
    staff_token_with_admin_claim = create_access_token(staff.id, "admin")

    resolved_admin = get_current_user(
        make_request(cookie=admin_token_with_staff_claim),
        db,
    )
    assert get_current_admin_user(resolved_admin) is admin

    resolved_staff = get_current_user(
        make_request(cookie=staff_token_with_admin_claim),
        db,
    )
    with pytest.raises(HTTPException) as error:
        get_current_admin_user(resolved_staff)

    assert error.value.status_code == 403


def test_inactive_admin_token_is_rejected(auth_context):
    db, _, _, inactive_admin = auth_context
    token = create_access_token(inactive_admin.id, "admin")

    with pytest.raises(HTTPException) as error:
        get_current_user(make_request(cookie=token), db)

    assert error.value.status_code == 401
