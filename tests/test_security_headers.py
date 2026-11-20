import asyncio

from starlette.requests import Request
from starlette.responses import Response

from config.settings import Settings
from middleware.security_headers import SecurityHeadersMiddleware


def request():
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def test_security_headers_are_set_for_all_environments(monkeypatch):
    monkeypatch.setattr(
        "middleware.security_headers.get_settings",
        lambda: Settings(_env_file=None, environment="development"),
    )
    middleware = SecurityHeadersMiddleware(lambda *_args: None)
    async def call_next(_request):
        return Response("ok")

    response = asyncio.run(middleware.dispatch(request(), call_next))

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "strict-transport-security" not in response.headers


def test_hsts_is_enabled_only_for_production(monkeypatch):
    monkeypatch.setattr(
        "middleware.security_headers.get_settings",
        lambda: Settings(_env_file=None, environment="production"),
    )
    middleware = SecurityHeadersMiddleware(lambda *_args: None)
    async def call_next(_request):
        return Response("ok")

    response = asyncio.run(middleware.dispatch(request(), call_next))

    assert response.headers["strict-transport-security"] == "max-age=15552000"
