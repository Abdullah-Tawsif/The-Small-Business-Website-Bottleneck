"""Business logic for creating and managing customer leads."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.lead import Lead
from models.package import Package
from schemas.lead import LeadCreate, LeadStatus
from services.pricing_service import calculate_project_estimate


ALLOWED_LEAD_STATUSES: tuple[str, ...] = (
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
    "won",
    "lost",
)


class LeadServiceError(Exception):
    """Raised when a lead operation cannot be completed."""


class PackageUnavailableError(LeadServiceError):
    """Raised when a customer selects a missing or inactive package."""


class LeadNotFoundError(LeadServiceError):
    """Raised when a requested lead does not exist."""


def create_lead(db: Session, lead_data: LeadCreate) -> Lead:
    """Validate package selection, calculate an estimate, and save a lead.

    If a package is selected, its price and the requested pages/features are
    passed through the existing pricing service. The resulting estimate is
    saved with the lead. Leads without a selected package are saved without
    an estimate.
    """
    try:
        lead_values = lead_data.model_dump()

        if lead_data.package_id is not None:
            package = db.get(Package, lead_data.package_id)
            if package is None or not package.is_active:
                raise PackageUnavailableError(
                    "Selected package is unavailable."
                )

            estimate = calculate_project_estimate(
                db=db,
                package_id=package.id,
                required_pages=lead_data.required_pages,
                required_features=lead_data.required_features,
            )
            lead_values["estimated_min_price"] = estimate[
                "estimated_min_price"
            ]
            lead_values["estimated_max_price"] = estimate[
                "estimated_max_price"
            ]
            lead_values["currency"] = estimate["currency"]

        new_lead = Lead(**lead_values, status="new")
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        return new_lead

    except PackageUnavailableError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise LeadServiceError(
            "The customer inquiry could not be saved."
        ) from exc


def get_lead_by_id(db: Session, lead_id: int) -> Lead | None:
    """Return one lead by its primary key, or None when it is absent."""
    return db.get(Lead, lead_id)


def list_leads(
    db: Session,
    *,
    status: LeadStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Lead]:
    """Return leads newest-first, optionally filtered by status.

    Pagination is bounded to avoid accidentally loading an unbounded number
    of rows. Authentication and authorization should be enforced by the API
    route that exposes this operation.
    """
    if skip < 0:
        raise ValueError("skip cannot be negative.")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    if status is not None and status not in ALLOWED_LEAD_STATUSES:
        raise ValueError("Invalid lead status.")

    statement = select(Lead)
    if status is not None:
        statement = statement.where(Lead.status == status)

    statement = (
        statement
        .order_by(Lead.created_at.desc(), Lead.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def update_lead_status(
    db: Session,
    lead_id: int,
    new_status: LeadStatus,
) -> Lead:
    """Update a lead's pipeline status and return the refreshed lead."""
    if new_status not in ALLOWED_LEAD_STATUSES:
        raise ValueError("Invalid lead status.")

    lead = db.get(Lead, lead_id)
    if lead is None:
        raise LeadNotFoundError(f"Lead {lead_id} was not found.")

    try:
        lead.status = new_status
        db.commit()
        db.refresh(lead)
        return lead
    except SQLAlchemyError as exc:
        db.rollback()
        raise LeadServiceError(
            "The lead status could not be updated."
        ) from exc
