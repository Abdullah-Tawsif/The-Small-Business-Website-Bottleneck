"""Protect browser state changes that use the authentication cookie."""

import hmac
import secrets
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config.settings import get_settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def set_csrf_cookie(response: Response) -> str:
    """Issue a fresh readable, same-site CSRF token cookie."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=settings.environment.lower() == "production",
        samesite="strict",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return token


def _origin_tuple(value: str) -> tuple[str, str, int] | None:
    """Normalize a serialized HTTP origin, rejecting non-origin URL parts."""
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        scheme = parsed.scheme.lower()
        port = parsed.port or (443 if scheme == "https" else 80)
        return scheme, parsed.hostname.lower(), port
    except ValueError:
        return None


def _request_origin(request: Request) -> tuple[str, str, int] | None:
    """Return the origin the ASGI server received for this request."""
    host = request.headers.get("host")
    if not host:
        return None
    scheme = request.url.scheme.lower()
    if scheme not in {"http", "https"}:
        return None
    return _origin_tuple(f"{scheme}://{host}")


def _referer_origin(value: str) -> tuple[str, str, int] | None:
    """Extract the origin from a Referer URL, which normally has a path."""
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return None
        return _origin_tuple(f"{parsed.scheme}://{parsed.netloc}")
    except ValueError:
        return None


def _is_cookie_authenticated_write(request: Request) -> bool:
    """Identify current state-changing routes authorized by the session cookie."""
    if request.method.upper() not in _UNSAFE_METHODS:
        return False
    if not request.cookies.get(get_settings().access_token_cookie_name):
        return False

    path = request.url.path
    if path == "/api/auth/logout":
        return True
    if path.startswith("/api/admin/"):
        return True
    if path.startswith("/api/leads/") and request.method.upper() in {
        "PATCH",
        "PUT",
        "DELETE",
    }:
        return True
    return False


def _requires_origin(request: Request) -> bool:
    """Require browser-origin evidence for cookie and authentication writes."""
    return _is_cookie_authenticated_write(request) or request.url.path in {
        "/api/auth/login",
        "/api/auth/register",
    }


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Validate request origins and double-submit tokens for cookie writes.

    Non-browser clients using bearer authorization remain usable without a
    CSRF token. Browser requests carrying the session cookie must send the
    readable CSRF cookie value in ``X-CSRF-Token`` for authenticated writes.
    Any supplied Origin or Referer must match this application's origin.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method.upper() not in _UNSAFE_METHODS:
            response = await call_next(request)
            if (
                request.method.upper() == "GET"
                and request.cookies.get(get_settings().access_token_cookie_name)
                and not request.cookies.get(CSRF_COOKIE_NAME)
            ):
                set_csrf_cookie(response)
            return response

        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site":
            return JSONResponse(
                status_code=403,
                content={"detail": "Cross-origin request rejected."},
            )

        origin_header = request.headers.get("origin")
        referer_header = request.headers.get("referer")
        supplied_origin = (
            _origin_tuple(origin_header)
            if origin_header is not None
            else _referer_origin(referer_header)
            if referer_header is not None
            else None
        )
        expected_origin = _request_origin(request)
        if supplied_origin is not None:
            if expected_origin is None or supplied_origin != expected_origin:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected."},
                )

        if _requires_origin(request) and supplied_origin is None:
            return JSONResponse(
                status_code=403,
                content={"detail": "Request origin is required."},
            )

        if _is_cookie_authenticated_write(request):
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
            header_token = request.headers.get(CSRF_HEADER_NAME, "")
            if (
                not cookie_token
                or not header_token
                or not hmac.compare_digest(cookie_token, header_token)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token is missing or invalid."},
                )

        return await call_next(request)
