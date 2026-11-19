
"""Public API routes for packages and project pricing."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import get_db
from models.package import Package
from schemas.package import PackageResponse
from services.pricing_service import calculate_project_estimate


router = APIRouter(
    prefix="/api",
    tags=["Public"],
)


class PriceEstimateRequest(BaseModel):
    """Customer requirements used to calculate a project estimate."""

    model_config = ConfigDict(extra="forbid")

    package_id: int = Field(gt=0)

    required_pages: list[str] = Field(
        default_factory=list,
        max_length=30,
    )

    required_features: list[str] = Field(
        default_factory=list,
        max_length=50,
    )


@router.get(
    "/packages/",
    response_model=list[PackageResponse],
    summary="Get available website packages",
)
def get_public_packages(
    db: Session = Depends(get_db),
) -> list[Package]:
    """Return active packages in their configured display order."""

    statement = (
        select(Package)
        .where(Package.is_active.is_(True))
        .order_by(
            Package.display_order.asc(),
            Package.id.asc(),
        )
    )

    return list(db.scalars(statement).all())


@router.post(
    "/packages/estimate",
    summary="Calculate website project pricing",
)
def estimate_project_price(
    payload: PriceEstimateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Calculate an estimated price using the selected package,
    requested pages and additional features.
    """

    try:
        estimate = calculate_project_estimate(
            db=db,
            package_id=payload.package_id,
            required_pages=payload.required_pages,
            required_features=payload.required_features,
        )

        return estimate

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
