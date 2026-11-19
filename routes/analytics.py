import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.auth_middleware import get_current_admin_user
from models.user import User
from schemas.analytics import AnalyticsDashboard, AnalyticsFilter
from services.analytics_service import get_analytics_dashboard


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Analytics"],
)


@router.get(
    "/analytics",
    response_model=AnalyticsDashboard,
    summary="Get agency analytics dashboard",
)
def read_analytics_dashboard(
    start_date: date = Query(
        ...,
        description="Start date in YYYY-MM-DD format.",
    ),
    end_date: date = Query(
        ...,
        description="End date in YYYY-MM-DD format.",
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Returns analytics for a selected date range.

    Only active administrators can access this endpoint.
    Authorization uses the current database user record.
    """

    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="End date cannot be earlier than start date.",
        )

    filters = AnalyticsFilter(
        start_date=start_date,
        end_date=end_date,
    )

    try:
        dashboard = get_analytics_dashboard(
            db=db,
            filters=filters,
        )

        return dashboard

    except SQLAlchemyError as exc:
        logger.exception(
            "Database error while generating analytics."
        )

        raise HTTPException(
            status_code=503,
            detail="Analytics service is temporarily unavailable.",
        ) from exc
