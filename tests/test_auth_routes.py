from fastapi import Response

from config.settings import get_settings
from models.user import User
from routes.auth import _clear_session_cookie, _set_session_cookie, logout


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
