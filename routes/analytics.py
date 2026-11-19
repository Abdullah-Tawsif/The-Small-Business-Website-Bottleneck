
import logging
from datetime import date
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.database import get_db

from schemas.analytics import (
    AnalyticsDashboard,
    AnalyticsFilter,
)

from services.analytics_service import get_analytics_dashboard

from utils.security import (
    SecurityError,
    decode_access_token,
)


# --------------------------------------------------
# 1. LOGGER CONFIGURATION
# --------------------------------------------------

logger = logging.getLogger(__name__)


# --------------------------------------------------
# 2. ROUTER CONFIGURATION
# --------------------------------------------------

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Analytics"],
)

bearer_scheme = HTTPBearer(auto_error=False)


# --------------------------------------------------
# 3. ADMIN AUTHENTICATION
# --------------------------------------------------

def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict[str, Any]:
    """
    Requires a valid JWT belonging to an admin.

    Uses the existing security utilities.
    """

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_access_token(
            credentials.credentials
        )

    except SecurityError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator access required.",
        )

    return claims


# --------------------------------------------------
# 4. GET ANALYTICS DASHBOARD
# --------------------------------------------------

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

    admin: dict[str, Any] = Depends(require_admin),
):
    """
    Returns analytics for a selected date range.

    Only authenticated administrators can access
    this endpoint.
    """

    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="End date cannot be earlier than start date.",
        )

    # Create validated filter object
    filters = AnalyticsFilter(
        start_date=start_date,
        end_date=end_date,
    )

    # Generate analytics
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
