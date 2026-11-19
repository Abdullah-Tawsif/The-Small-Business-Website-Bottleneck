
"""Administrator-only user management endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.auth_middleware import get_current_admin_user
from models.user import User


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin User Management"],
)


# --------------------------------------------------
# RESPONSE SCHEMAS
# --------------------------------------------------

class AdminUserListItem(BaseModel):
    """Safe public fields for administrator user management."""

    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    """Paginated administrator user listing."""

    items: list[AdminUserListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# --------------------------------------------------
# GET ALL USERS
# --------------------------------------------------

@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List all registered users",
)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Return a paginated list of users.

    Only active administrators can access this endpoint.
    Password hashes and other sensitive fields are never returned.
    """

    try:
        # Get total number of registered users.
        total = db.scalar(
            select(func.count()).select_from(User)
        ) or 0

        # Retrieve the requested page.
        users = db.scalars(
            select(User)
            .order_by(
                User.created_at.desc(),
                User.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        # Explicitly select safe fields.
        items = [
            AdminUserListItem(
                id=user.id,
                full_name=user.full_name,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
            )
            for user in users
        ]

        total_pages = (total + page_size - 1) // page_size

        return AdminUserListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Database error while retrieving administrator user list."
        )

        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve users at this time.",
        ) from exc
