from sqlalchemy import select
from sqlalchemy.orm import Session
from models.user import User
from utils.security import hash_password, verify_password


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def register_user(db: Session, *, full_name: str, email: str, password: str) -> User:
    normalized_email = email.lower().strip()
    if get_user_by_email(db, normalized_email):
        raise ValueError("An account with this email already exists.")
    user = User(full_name=full_name.strip(), email=normalized_email, hashed_password=hash_password(password), role="staff")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email.strip().lower())
    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user
