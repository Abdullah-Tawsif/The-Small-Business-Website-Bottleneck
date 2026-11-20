
"""API routes for customer lead submission and admin lead management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.auth_middleware import get_current_admin_user
from models.user import User
from schemas.lead import LeadCreate, LeadResponse, LeadStatus
from services.lead_service import (
    LeadNotFoundError,
    LeadServiceError,
    PackageUnavailableError,
)
from services.lead_service import (
    create_lead as create_lead_service,
)
from services.lead_service import (
    get_lead_by_id as get_lead_by_id_service,
)
from services.lead_service import (
    list_leads as list_leads_service,
)
from services.lead_service import (
    update_lead_status as update_lead_status_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
)


class LeadStatusUpdate(BaseModel):
    """Request body for updating a lead's pipeline status."""

    model_config = ConfigDict(extra="forbid")

    status: LeadStatus


def _database_error() -> HTTPException:
    """Return a consistent database service-unavailable response."""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database temporarily unavailable.",
    )


# --------------------------------------------------
# 1. PUBLIC CUSTOMER LEAD SUBMISSION
# --------------------------------------------------

@router.post(
    "/",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a customer inquiry",
)
def submit_lead(
    lead_data: LeadCreate,
    db: Session = Depends(get_db),
):
    """
    Public endpoint for customer inquiry submission.

    Business logic, package validation and pricing calculations
    are delegated to the existing lead service.
    """

    try:
        return create_lead_service(
            db=db,
            lead_data=lead_data,
        )

    except PackageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except LeadServiceError as exc:
        logger.exception("Lead creation failed.")
        raise _database_error() from exc

    except SQLAlchemyError as exc:
        logger.exception("Database error while creating lead.")
        raise _database_error() from exc


# --------------------------------------------------
# 2. ADMIN LEAD LISTING
# --------------------------------------------------

@router.get(
    "/",
    response_model=list[LeadResponse],
    summary="List customer leads",
)
def read_leads(
    lead_status: LeadStatus | None = Query(
        default=None,
        alias="status",
        description="Filter leads by pipeline status.",
    ),
    skip: int = Query(
        default=0,
        ge=0,
        description="Number of leads to skip.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of leads to return.",
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Retrieve leads with optional status filtering and pagination."""

    try:
        return list_leads_service(
            db=db,
            status=lead_status,
            skip=skip,
            limit=limit,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except SQLAlchemyError as exc:
        logger.exception("Database error while listing leads.")
        raise _database_error() from exc


# --------------------------------------------------
# 3. ADMIN SINGLE LEAD RETRIEVAL
# --------------------------------------------------

@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Get lead by ID",
)
def read_lead(
    lead_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Retrieve an individual customer lead."""

    try:
        lead = get_lead_by_id_service(
            db=db,
            lead_id=lead_id,
        )

        if lead is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found.",
            )

        return lead

    except HTTPException:
        raise

    except SQLAlchemyError as exc:
        logger.exception("Database error while retrieving lead.")
        raise _database_error() from exc


# --------------------------------------------------
# 4. ADMIN LEAD STATUS UPDATE
# --------------------------------------------------

@router.patch(
    "/{lead_id}/status",
    response_model=LeadResponse,
    summary="Update lead status",
)
def change_lead_status(
    lead_id: Annotated[int, Path(ge=1)],
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Update a lead's pipeline status.

    Accepted statuses:
    new, contacted, qualified, proposal_sent, won, lost.
    """

    try:
        return update_lead_status_service(
            db=db,
            lead_id=lead_id,
            new_status=payload.status,
        )

    except LeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except LeadServiceError as exc:
        logger.exception("Lead status update failed.")
        raise _database_error() from exc

    except SQLAlchemyError as exc:
        logger.exception("Database error while updating lead status.")
        raise _database_error() from exc
