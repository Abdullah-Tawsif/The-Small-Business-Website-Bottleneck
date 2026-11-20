
"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
def login(
    payload: LoginInput,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate an active user and establish a session."""

    user = authenticate_user(
        db,
        email=str(payload.email),
        password=payload.password,
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

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
