
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.database import get_db
from models.lead import Lead
from models.package import Package
from schemas.lead import LeadCreate, LeadResponse


# --------------------------------------------------
# 1. ROUTER CONFIGURATION
# --------------------------------------------------

router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
)


# --------------------------------------------------
# 2. CREATE A NEW LEAD
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
    Receives a customer inquiry and saves it
    as a new lead in PostgreSQL.
    """

    # Verify that the selected package exists
    if lead_data.package_id is not None:

        package = db.get(Package, lead_data.package_id)

        if package is None or not package.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Selected package does not exist or is unavailable.",
            )

    # Convert validated Pydantic data into a dictionary
    lead_data_dict = lead_data.model_dump()

    # Create SQLAlchemy lead object
    new_lead = Lead(
        **lead_data_dict,
        status="new",
    )

    # Save lead in PostgreSQL
    try:
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to save lead because of invalid data.",
        )

    return new_lead


# --------------------------------------------------
# 3. CHECK LEAD EXISTENCE
# --------------------------------------------------

@router.get(
    "/check/{lead_id}",
)
def check_lead(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """
    Checks whether a lead exists.

    Returns only basic information, not private
    customer or project details.
    """

    lead = db.get(Lead, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        )

    return {
        "id": lead.id,
        "status": lead.status,
        "created_at": lead.created_at,
        "exists": True,
    }
