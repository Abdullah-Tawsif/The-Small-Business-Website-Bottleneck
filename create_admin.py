
#!/usr/bin/env python3
"""Create an administrator account securely.

Usage:
    python create_admin.py
"""

import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import SessionLocal, verify_schema
from models.user import User
from utils.security import PasswordError, hash_password


def find_user_by_email(db: Session, email: str):
    """Find an existing account using case-insensitive email matching."""
    return db.scalar(
        select(User).where(
            func.lower(User.email) == email.lower()
        )
    )


def create_admin_account(
    db: Session,
    full_name: str,
    email: str,
    password: str,
):
    """Create a new active administrator."""

    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name or len(full_name) > 100:
        raise ValueError("Invalid full name.")

    if not email or len(email) > 254:
        raise ValueError("Invalid email address.")

    try:
        existing_user = find_user_by_email(db, email)

        if existing_user:
            raise ValueError(
                "This email already exists. No account was modified."
            )

        # Existing security utility enforces 10-128 characters.
        hashed_password = hash_password(password)

        admin = User(
            full_name=full_name,
            email=email,
            hashed_password=hashed_password,
            role="admin",
            is_active=True,
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        return admin

    except IntegrityError as exc:
        db.rollback()

        if find_user_by_email(db, email):
            raise ValueError(
                "This email already exists. No account was modified."
            ) from exc

        raise

    except SQLAlchemyError:
        db.rollback()
        raise


def main():
    """Interactive administrator creation."""

    try:
        verify_schema()
    except RuntimeError as exc:
        print(f"Database schema is not ready: {exc}")
        return 1
    except SQLAlchemyError:
        print("Database schema verification failed.")
        return 1

    print("\n=== Initial Administrator Setup ===\n")

    full_name = input("Administrator full name: ").strip()

    if not full_name or len(full_name) > 100:
        print("Invalid full name.")
        return 1

    raw_email = input("Administrator email: ").strip()

    try:
        email = str(
            TypeAdapter(EmailStr).validate_python(raw_email)
        ).lower()
    except ValidationError:
        print("Please enter a valid email address.")
        return 1

    password = getpass.getpass(
        "Administrator password (10-128 characters): "
    )

    try:
        with SessionLocal() as db:
            admin = create_admin_account(
                db=db,
                full_name=full_name,
                email=email,
                password=password,
            )

        print(
            f"\nAdministrator created successfully: {admin.email}"
        )
        return 0

    except PasswordError as exc:
        print(f"Password rejected: {exc}")
        return 1

    except ValueError as exc:
        print(str(exc))
        return 1

    except SQLAlchemyError:
        print("Database error. Administrator creation failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
