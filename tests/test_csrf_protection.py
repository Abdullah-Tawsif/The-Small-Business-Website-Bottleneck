import asyncio

import pytest
from starlette.requests import Request
from starlette.responses import Response

import middleware.csrf_protection as csrf_module
from config.settings import Settings
from middleware.csrf_protection import CSRFProtectionMiddleware


def make_request(
    *,
    method="PATCH",
    path="/api/admin/users/2/status",
    origin="http://app.example",
    referer=None,
    csrf_cookie="valid-token",
    csrf_header="valid-token",
    fetch_site=None,
    authorization=None,
):
    headers = [(b"host", b"app.example")]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    if referer is not None:
        headers.append((b"referer", referer.encode("ascii")))
    if csrf_header is not None:
        headers.append((b"x-csrf-token", csrf_header.encode("ascii")))
    cookies = ["access_token=session-token"]
    if csrf_cookie is not None:
        cookies.append(f"csrf_token={csrf_cookie}")
    headers.append((b"cookie", "; ".join(cookies).encode("ascii")))
    if fetch_site is not None:
        headers.append((b"sec-fetch-site", fetch_site.encode("ascii")))
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "path": path,
            "headers": headers,
            "client": ("192.0.2.10", 1234),
        }
    )


def dispatch(request):
    middleware = CSRFProtectionMiddleware(lambda *_args: None)
    reached_application = False

    async def call_next(_request):
        nonlocal reached_application
        reached_application = True
        return Response("ok")

    response = asyncio.run(middleware.dispatch(request, call_next))
    return response, reached_application


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setattr(
        csrf_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            jwt_secret_key="csrf-test-only-secret-material-at-least-32-bytes",
        ),
    )


def test_cookie_authenticated_write_rejects_missing_origin():
    response, reached = dispatch(make_request(origin=None))
    assert response.status_code == 403
    assert not reached


@pytest.mark.parametrize("origin", ["http://attacker.example", "null", "http://app.example/extra"])
def test_cross_origin_and_malformed_origins_are_rejected(origin):
    response, reached = dispatch(make_request(origin=origin))
    assert response.status_code == 403
    assert not reached


def test_cookie_authenticated_write_rejects_missing_csrf_token():
    response, reached = dispatch(make_request(csrf_header=None))
    assert response.status_code == 403
    assert not reached


def test_cookie_authenticated_write_rejects_missing_csrf_cookie():
    response, reached = dispatch(make_request(csrf_cookie=None))
    assert response.status_code == 403
    assert not reached


def test_cookie_authenticated_write_rejects_mismatched_csrf_token():
    response, reached = dispatch(make_request(csrf_header="different-token"))
    assert response.status_code == 403
    assert not reached


def test_same_origin_and_matching_csrf_token_are_accepted():
    response, reached = dispatch(make_request())
    assert response.status_code == 200
    assert reached


def test_same_origin_referer_is_accepted_when_origin_header_is_absent():
    response, reached = dispatch(
        make_request(origin=None, referer="http://app.example/admin")
    )
    assert response.status_code == 200
    assert reached


def test_cross_site_fetch_metadata_is_rejected():
    response, reached = dispatch(make_request(fetch_site="cross-site"))
    assert response.status_code == 403
    assert not reached


def test_bearer_authenticated_write_does_not_require_cookie_csrf_token():
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "scheme": "http",
            "path": "/api/admin/users/2/status",
            "headers": [
                (b"host", b"app.example"),
                (b"authorization", b"Bearer api-token"),
            ],
        }
    )
    response, reached = dispatch(request)
    assert response.status_code == 200
    assert reached


def test_logout_requires_csrf_for_an_existing_cookie_session():
    response, reached = dispatch(
        make_request(path="/api/auth/logout", method="POST", csrf_header=None)
    )
    assert response.status_code == 403
    assert not reached


def test_admin_lead_status_update_requires_csrf_and_accepts_matching_token():
    rejected, reached = dispatch(
        make_request(path="/api/leads/123/status", csrf_header=None)
    )
    assert rejected.status_code == 403
    assert not reached

    accepted, reached = dispatch(
        make_request(path="/api/leads/123/status")
    )
    assert accepted.status_code == 200
    assert reached


def test_public_registration_rejects_a_forged_origin():
    response, reached = dispatch(
        make_request(
            path="/api/auth/register",
            method="POST",
            origin="http://attacker.example",
            csrf_cookie=None,
            csrf_header=None,
        )
    )
    assert response.status_code == 403
    assert not reached


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register"])
def test_authentication_writes_require_origin_evidence(path):
    response, reached = dispatch(
        make_request(path=path, method="POST", origin=None)
    )
    assert response.status_code == 403
    assert not reached

    response, reached = dispatch(
        make_request(path=path, method="POST", origin="http://app.example")
    )
    assert response.status_code == 200
    assert reached
