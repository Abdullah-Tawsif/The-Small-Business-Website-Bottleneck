
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db
from models.lead import Lead
from models.package import Package
from schemas.lead import LeadCreate, LeadResponse


logger = logging.getLogger(__name__)


# --------------------------------------------------
# 1. ROUTER CONFIGURATION
# --------------------------------------------------

router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
)


# --------------------------------------------------
# 2. CREATE CUSTOMER LEAD
# --------------------------------------------------

@router.post(
    "/",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lead(
    lead_data: LeadCreate,
    db: Session = Depends(get_db),
):
    """
    Creates a new customer inquiry.

    Validates the selected package,
    saves the lead and returns the result.
    """

    # Verify selected package
    if lead_data.package_id is not None:

        package = db.get(
            Package,
            lead_data.package_id,
        )

        if package is None or not package.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Selected package is unavailable.",
            )

    # Create lead object
    new_lead = Lead(
        **lead_data.model_dump(),
        status="new",
    )

    # Save to PostgreSQL
    try:
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)

    except IntegrityError as exc:
        db.rollback()

        logger.warning(
            "Lead creation failed due to invalid database data."
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to save customer inquiry.",
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Database error while creating customer lead."
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable.",
        ) from exc

    return new_lead
