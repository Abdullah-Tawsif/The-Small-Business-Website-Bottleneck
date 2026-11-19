from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from database.database import get_db
from middleware.auth_middleware import get_current_user
from models.user import User
from schemas.user import UserPublic
from services.auth_service import authenticate_user, register_user
from utils.security import PasswordError, create_access_token
from utils.validators import LoginInput, RegistrationInput
from config.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    token = create_access_token(user.id, user.role, settings.access_token_expire_minutes)
    response.set_cookie(
        key="access_token", value=token, httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax", max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegistrationInput, response: Response, db: Session = Depends(get_db)):
    try:
        user = register_user(db, full_name=payload.full_name, email=str(payload.email), password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _set_session_cookie(response, user)
    return {"message": "Account created successfully.", "redirect_url": "/dashboard", "user": UserPublic.model_validate(user).model_dump(mode="json")}

@router.post("/login")
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, email=str(payload.email), password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    _set_session_cookie(response, user)
    return {"message": "Signed in successfully.", "redirect_url": "/dashboard", "user": UserPublic.model_validate(user).model_dump(mode="json")}

@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)):
    return user

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token", path="/", httponly=True, samesite="lax")
    return {"message": "Signed out successfully.", "redirect_url": "/login"}
