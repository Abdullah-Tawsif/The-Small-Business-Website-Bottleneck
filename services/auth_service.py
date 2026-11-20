"""Database operations for registration and login."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.user import User
from utils.security import hash_password, verify_password


# A syntactically valid hash with a fixed salt and an unreachable zero digest.
# It equalizes password-hash work for unknown accounts without creating a
# usable credential.
_DUMMY_PASSWORD_HASH = (
    "scrypt$16384$8$1$"
    + "00" * 16
    + "$"
    + "00" * 32
)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Find a user using a normalized email address."""
    normalized_email = email.strip().lower()

    return db.scalar(
        select(User).where(User.email == normalized_email)
    )


def register_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
) -> User:
    """Register a public account with the least-privileged staff role."""

    normalized_email = email.strip().lower()
    normalized_name = full_name.strip()

    if not normalized_name:
        raise ValueError("Full name is required.")

    if get_user_by_email(db, normalized_email):
        raise ValueError(
            "An account with this email already exists."
        )

    user = User(
        full_name=normalized_name,
        email=normalized_email,
        hashed_password=hash_password(password),
        role="staff",
    )

    db.add(user)

    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        # The database unique constraint protects against
        # simultaneous registrations using the same email.
        if get_user_by_email(db, normalized_email):
            raise ValueError(
                "An account with this email already exists."
            ) from exc

        raise

    db.refresh(user)

    return user


def authenticate_user(
    db: Session,
    *,
    email: str,
    password: str,
) -> User | None:
    """Authenticate an active user without revealing account status."""

    user = get_user_by_email(db, email)

    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None

    # Check the password even for disabled accounts so the
    # response does not disclose whether the account is active.
    password_is_valid = verify_password(
        password,
        user.hashed_password,
    )

    if not user.is_active or not password_is_valid:
        return None

    return user
