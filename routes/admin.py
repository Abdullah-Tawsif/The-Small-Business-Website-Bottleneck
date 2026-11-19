
"""Administrator-only user management endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict
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
    """Safe user information."""

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


class StaffAccountStatusUpdate(BaseModel):
    """Only the active status may be changed."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool


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
    """Return a paginated list of users."""

    try:
        total = db.scalar(
            select(func.count()).select_from(User)
        ) or 0

        users = db.scalars(
            select(User)
            .order_by(
                User.created_at.desc(),
                User.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

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


# --------------------------------------------------
# ACTIVATE / DEACTIVATE STAFF ACCOUNT
# --------------------------------------------------

@router.patch(
    "/users/{user_id}/status",
    response_model=AdminUserListItem,
    summary="Activate or deactivate a staff account",
)
def update_staff_account_status(
    user_id: int = Path(..., ge=1),
    payload: StaffAccountStatusUpdate = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Change the active status of an existing staff account.

    Administrator accounts cannot be modified through this endpoint.
    Account roles are never changed.
    """

    try:
        target_user = db.scalar(
            select(User)
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )

        if target_user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found.",
            )

        # Only staff accounts can be activated or deactivated.
        if target_user.role != "staff":
            raise HTTPException(
                status_code=403,
                detail="Only staff accounts can be modified through this endpoint.",
            )

        target_user.is_active = payload.is_active

        db.commit()
        db.refresh(target_user)

        return AdminUserListItem(
            id=target_user.id,
            full_name=target_user.full_name,
            email=target_user.email,
            role=target_user.role,
            is_active=target_user.is_active,
            created_at=target_user.created_at,
        )

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Database error while updating staff account status."
        )

        raise HTTPException(
            status_code=503,
            detail="Unable to update account status at this time.",
        ) from exc
