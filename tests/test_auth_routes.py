import asyncio
from types import SimpleNamespace

from fastapi import Response
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from config.settings import get_settings
from models.user import User
from routes.auth import (
    _account_key,
    _attempt_count,
    _clear_session_cookie,
    _record_failed_login,
    _set_session_cookie,
    login,
    logout,
)
from utils.security import hash_password
from utils.validators import LoginInput


def test_session_cookie_uses_http_only_lax_and_configured_lifetime(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-cookie-test-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    get_settings.cache_clear()
    response = Response()

    _set_session_cookie(
        response,
        User(id=17, full_name="Test User", email="test@example.com", role="staff"),
    )

    cookies = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]
    cookie = next(value for value in cookies if value.startswith("access_token="))
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=2700" in cookie
    assert "Secure" not in cookie
    csrf_cookie = next(value for value in cookies if value.startswith("csrf_token="))
    assert "SameSite=strict" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Max-Age=2700" in csrf_cookie
    get_settings.cache_clear()


def test_session_cookie_is_secure_in_production(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-cookie-test-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    response = Response()

    _set_session_cookie(
        response,
        User(id=17, full_name="Test User", email="test@example.com", role="admin"),
    )

    assert "Secure" in response.headers["set-cookie"]
    get_settings.cache_clear()


def test_logout_clears_the_session_cookie_with_matching_security_flags(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-cookie-test-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    response = Response()

    result = logout(response)

    cookies = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]
    cookie = next(value for value in cookies if value.startswith("access_token="))
    csrf_cookie = next(value for value in cookies if value.startswith("csrf_token="))
    assert result["redirect_url"] == "/login"
    assert 'access_token=""' in cookie
    assert "Max-Age=0" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "csrf_token=\"\"" in csrf_cookie
    assert "Max-Age=0" in csrf_cookie
    assert "Secure" in csrf_cookie
    assert "SameSite=strict" in csrf_cookie
    get_settings.cache_clear()


def test_cookie_clear_helper_removes_cookie():
    response = Response()

    _clear_session_cookie(response)

    cookies = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]
    assert any(value.startswith("access_token=\"\"") and "Max-Age=0" in value for value in cookies)
    assert any(value.startswith("csrf_token=\"\"") and "Max-Age=0" in value for value in cookies)


class LoginFailureRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def eval(self, _script, _keys, key, _ttl):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    async def delete(self, key):
        return self.values.pop(key, None) is not None


def _login_request(client_ip, store):
    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=store))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [],
        "client": (client_ip, 12345),
        "app": app,
    })


def _active_user_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'login-lockout.sqlite'}")
    from models.user import User

    User.__table__.create(engine)
    db = Session(engine, expire_on_commit=False)
    user = User(
        full_name="Login User",
        email="person@example.com",
        hashed_password=hash_password("valid-login-password-123"),
        role="staff",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return engine, db, user


def _run_login(request, db, email, password):
    return asyncio.run(login(
        request,
        LoginInput(email=email, password=password),
        Response(),
        db,
    ))


def test_login_failures_share_normalized_hashed_account_identity(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-account-limit-secret-at-least-32-bytes")
    get_settings.cache_clear()
    store = LoginFailureRedis()
    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=store))
    request_a = Request({"type": "http", "method": "POST", "headers": [], "client": ("192.0.2.1", 1), "app": app})
    request_b = Request({"type": "http", "method": "POST", "headers": [], "client": ("192.0.2.2", 1), "app": app})
    key_a = _account_key(" User@Example.com ")
    key_b = _account_key("user@example.com")
    assert key_a == key_b
    assert "user@example.com" not in key_a

    async def attack():
        for _ in range(4):
            await _record_failed_login(request_a, key_a)
        return await _attempt_count(request_b, key_b)

    assert asyncio.run(attack()) == 4
    get_settings.cache_clear()


def test_correct_login_succeeds_after_eight_failed_attempts(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-account-limit-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    engine, db, _user = _active_user_db(tmp_path)
    store = LoginFailureRedis()

    async def no_delay(_seconds):
        return None

    monkeypatch.setattr("routes.auth.asyncio.sleep", no_delay)
    try:
        for _ in range(8):
            with pytest.raises(HTTPException) as failure:
                _run_login(
                    _login_request("192.0.2.10", store),
                    db,
                    "person@example.com",
                    "incorrect-password-123",
                )
            assert failure.value.status_code == 401

        result = _run_login(
            _login_request("192.0.2.10", store),
            db,
            "person@example.com",
            "valid-login-password-123",
        )
        assert result["message"] == "Signed in successfully."
        assert result["user"]["email"] == "person@example.com"
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()


def test_distributed_failures_apply_bounded_friction_without_denial(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-account-limit-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    engine, db, _user = _active_user_db(tmp_path)
    store = LoginFailureRedis()
    delays = []

    async def record_delay(seconds):
        delays.append(seconds)

    monkeypatch.setattr("routes.auth.asyncio.sleep", record_delay)
    try:
        for ip in ("192.0.2.11", "192.0.2.12", "192.0.2.13"):
            with pytest.raises(HTTPException) as failure:
                _run_login(
                    _login_request(ip, store),
                    db,
                    "person@example.com",
                    "incorrect-password-123",
                )
            assert failure.value.status_code == 401

        assert len(store.values) == 1
        assert next(iter(store.values.values())) == 3
        assert delays == [0.25]
        result = _run_login(
            _login_request("192.0.2.14", store),
            db,
            "person@example.com",
            "valid-login-password-123",
        )
        assert result["message"] == "Signed in successfully."
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()


def test_repeated_account_failures_never_create_a_permanent_lockout(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-account-limit-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    engine, db, _user = _active_user_db(tmp_path)
    store = LoginFailureRedis()
    try:
        request = _login_request("192.0.2.20", store)
        account_key = _account_key("person@example.com")
        for _ in range(100):
            asyncio.run(_record_failed_login(request, account_key))
        assert asyncio.run(_attempt_count(request, account_key)) == 100

        result = _run_login(
            request, db, "person@example.com", "valid-login-password-123"
        )
        assert result["message"] == "Signed in successfully."
        assert asyncio.run(_attempt_count(request, account_key)) == 0
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()


def test_unknown_and_existing_accounts_have_same_failed_login_response(
    monkeypatch, tmp_path
):
    import services.auth_service as auth_service

    monkeypatch.setenv("JWT_SECRET_KEY", "isolated-account-limit-secret-at-least-32-bytes")
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    engine, db, user = _active_user_db(tmp_path)
    store = LoginFailureRedis()
    try:
        observed_hashes = []
        real_verify = auth_service.verify_password

        def capture_verify(password, encoded_hash):
            observed_hashes.append(encoded_hash)
            return real_verify(password, encoded_hash)

        monkeypatch.setattr(auth_service, "verify_password", capture_verify)
        responses = []
        for ip, email in (
            ("192.0.2.31", "person@example.com"),
            ("192.0.2.32", "missing@example.com"),
        ):
            with pytest.raises(HTTPException) as failure:
                _run_login(
                    _login_request(ip, store),
                    db,
                    email,
                    "incorrect-password-123",
                )
            responses.append((failure.value.status_code, failure.value.detail))

        assert responses == [(401, "Incorrect email or password.")] * 2
        assert len(observed_hashes) == 2
        assert user.hashed_password in observed_hashes
        assert len(set(observed_hashes)) == 2
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()
