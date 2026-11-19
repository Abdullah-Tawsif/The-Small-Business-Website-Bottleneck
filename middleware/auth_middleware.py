from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from database.database import get_db
from models.user import User
from utils.security import InvalidTokenError, decode_access_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in to continue.")
    try:
        claims = decode_access_token(token)
        user_id = int(claims["sub"])
    except (InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Your session is invalid or has expired. Please sign in again.")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="This account is unavailable. Please sign in again.")
    return user
