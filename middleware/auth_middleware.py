"""Database-backed authentication and authorization dependencies."""

import hmac

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.database import get_db
from models.user import User
from utils.security import InvalidTokenError, decode_access_token


def _unauthorized(
    detail: str = "Authentication is required or the session is invalid."
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_access_token(request: Request) -> str:
    """Accept a cookie or Bearer token, rejecting conflicting credentials."""
    cookie_name = get_settings().access_token_cookie_name
    cookie_token = request.cookies.get(cookie_name)

    authorization = request.headers.get("Authorization")
    bearer_token = None

    if authorization is not None:
        parts = authorization.strip().split()

        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise _unauthorized(
                "Authorization must use the Bearer scheme."
            )

        bearer_token = parts[1]

    if cookie_token and bearer_token:
        if not hmac.compare_digest(
            cookie_token.encode("utf-8"),
            bearer_token.encode("utf-8"),
        ):
            raise _unauthorized(
                "Conflicting cookie and Bearer credentials were supplied."
            )

    token = cookie_token or bearer_token

    if not token:
        raise _unauthorized("Please sign in to continue.")

    if len(token) > 8192:
        raise _unauthorized("The supplied access token is invalid.")

    return token


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve the token subject to a fresh database row."""

    token = _extract_access_token(request)

    try:
        claims = decode_access_token(token)
        user_id = int(claims["sub"])

    except (InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise _unauthorized(
            "Your session is invalid or has expired. Please sign in again."
        ) from exc

    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )

    if user is None or not user.is_active:
        raise _unauthorized(
            "This account is unavailable. Please sign in again."
        )

    return user


def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """Return an authenticated user when credentials are present, else None."""
    if not request.cookies.get(get_settings().access_token_cookie_name) and not request.headers.get(
        "Authorization"
    ):
        return None
    return get_current_user(request, db)


def get_current_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """
    Require the user's CURRENT database role to be admin.

    Never trust the JWT role claim for authorization.
    """

    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    return user
