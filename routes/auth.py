
"""Authentication API endpoints."""

import asyncio
import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.database import get_db
from middleware.csrf_protection import CSRF_COOKIE_NAME, set_csrf_cookie
from middleware.auth_middleware import get_current_user
from models.user import User
from schemas.user import UserPublic
from services.auth_service import authenticate_user, register_user
from utils.security import PasswordError, create_access_token
from utils.validators import LoginInput, RegistrationInput


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)

_FAILED_LOGIN_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""
_LOCAL_FAILURES: dict[str, tuple[int, float]] = {}


def _account_key(email: str) -> str:
    """Return a keyed, normalized identifier suitable for a shared Redis key."""
    normalized = email.strip().casefold()
    secret = get_settings().jwt_secret_key.encode("utf-8")
    digest = hmac.new(secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"agencyforge:login-failures:v1:{digest}"


async def _attempt_count(request: Request, key: str) -> int:
    """Read recent failure count; production requires the shared Redis store."""
    settings = get_settings()
    redis_client = getattr(request.app.state, "rate_limit_redis", None)
    if redis_client is not None:
        return int(await redis_client.get(key) or 0)
    if settings.environment.lower() == "production":
        raise HTTPException(503, "Sign-in protection is temporarily unavailable.")
    current = _LOCAL_FAILURES.get(key)
    if current is None or current[1] <= time.monotonic():
        _LOCAL_FAILURES.pop(key, None)
        return 0
    return current[0]


async def _record_failed_login(request: Request, key: str) -> int:
    """Record a short-lived failure and return its count."""
    settings = get_settings()
    redis_client = getattr(request.app.state, "rate_limit_redis", None)
    if redis_client is not None:
        return int(await redis_client.eval(_FAILED_LOGIN_SCRIPT, 1, key, 900))
    if settings.environment.lower() == "production":
        raise HTTPException(503, "Sign-in protection is temporarily unavailable.")
    current = _LOCAL_FAILURES.get(key)
    count = current[0] + 1 if current and current[1] > time.monotonic() else 1
    _LOCAL_FAILURES[key] = (count, time.monotonic() + 900)
    return count


def _set_session_cookie(response: Response, user: User) -> None:
    """Create an access token and set the configured HttpOnly cookie."""

    settings = get_settings()

    token = create_access_token(
        user.id,
        user.role,
        settings.access_token_expire_minutes,
    )

    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=token,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    set_csrf_cookie(response)


def _clear_session_cookie(response: Response) -> None:
    """Remove the same configured cookie used during authentication."""

    settings = get_settings()

    response.delete_cookie(
        key=settings.access_token_cookie_name,
        path="/",
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        secure=settings.environment.lower() == "production",
        samesite="strict",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegistrationInput,
    response: Response,
    db: Session = Depends(get_db),
):
    """Register a new staff account and establish its session."""

    try:
        user = register_user(
            db,
            full_name=payload.full_name,
            email=str(payload.email),
            password=payload.password,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except PasswordError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    _set_session_cookie(response, user)

    return {
        "message": "Account created successfully.",
        "redirect_url": "/dashboard",
        "user": UserPublic.model_validate(user).model_dump(
            mode="json"
        ),
    }


@router.post("/login")
async def login(
    request: Request,
    payload: LoginInput,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate an active user and establish a session."""

    account_key = _account_key(str(payload.email))
    try:
        # Account failures add bounded friction after authentication fails, but
        # never reject a correct password: unauthenticated callers must not be
        # able to lock an account by driving this counter upward.
        prior_failures = await _attempt_count(request, account_key)
    except RedisError as exc:
        raise HTTPException(503, "Sign-in protection is temporarily unavailable.") from exc

    user = authenticate_user(
        db,
        email=str(payload.email),
        password=payload.password,
    )

    if user is None:
        try:
            failures = await _record_failed_login(request, account_key)
        except RedisError as exc:
            raise HTTPException(
                503, "Sign-in protection is temporarily unavailable."
            ) from exc
        failures = max(prior_failures, failures)
        if failures >= 3:
            await asyncio.sleep(min(0.25 * (2 ** min(failures - 3, 3)), 2.0))
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

    redis_client = getattr(request.app.state, "rate_limit_redis", None)
    try:
        if redis_client is not None:
            await redis_client.delete(account_key)
        else:
            _LOCAL_FAILURES.pop(account_key, None)
    except RedisError as exc:
        if get_settings().environment.lower() == "production":
            raise HTTPException(
                503, "Sign-in protection is temporarily unavailable."
            ) from exc

    _set_session_cookie(response, user)

    return {
        "message": "Signed in successfully.",
        "redirect_url": "/dashboard",
        "user": UserPublic.model_validate(user).model_dump(
            mode="json"
        ),
    }


@router.get(
    "/me",
    response_model=UserPublic,
)
def me(
    user: User = Depends(get_current_user),
):
    """Return the currently authenticated database user."""

    return user


@router.post("/logout")
def logout(response: Response):
    """Clear the configured authentication cookie."""

    _clear_session_cookie(response)

    return {
        "message": "Signed out successfully.",
        "redirect_url": "/login",
    }
