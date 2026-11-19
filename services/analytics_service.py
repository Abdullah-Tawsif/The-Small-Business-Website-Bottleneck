
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from models.lead import Lead
from models.package import Package

from schemas.analytics import (
    AnalyticsFilter,
    AnalyticsDashboard,
    LeadAnalytics,
    LeadStatusCount,
    PipelineAnalytics,
    PackagePerformance,
)


# --------------------------------------------------
# 1. ANALYTICS CONFIGURATION
# --------------------------------------------------

BANGLADESH_TIMEZONE = ZoneInfo("Asia/Dhaka")

BASE_CURRENCY = "BDT"

LEAD_STATUSES = [
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
    "won",
    "lost",
]

OPEN_STATUSES = [
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
]


# --------------------------------------------------
# 2. HELPER FUNCTIONS
# --------------------------------------------------

def to_decimal(value) -> Decimal:
    """
    Safely converts database numeric results into Decimal.
    """

    if value is None:
        return Decimal("0.00")

    return Decimal(str(value))


def get_date_range(filters: AnalyticsFilter):
    """
    Converts the requested Bangladesh calendar dates
    into timezone-aware timestamps.

    The end date is inclusive.
    """

    start_datetime = datetime.combine(
        filters.start_date,
        time.min,
        tzinfo=BANGLADESH_TIMEZONE,
    )

    end_datetime = datetime.combine(
        filters.end_date + timedelta(days=1),
        time.min,
        tzinfo=BANGLADESH_TIMEZONE,
    )

    return start_datetime, end_datetime


# --------------------------------------------------
# 3. LEAD ANALYTICS
# --------------------------------------------------

def calculate_lead_analytics(
    db: Session,
    start_datetime: datetime,
    end_datetime: datetime,
) -> LeadAnalytics:
    """
    Calculates total leads, status distribution
    and conversion rate.
    """

    filters = (
        Lead.created_at >= start_datetime,
        Lead.created_at < end_datetime,
        Lead.currency == BASE_CURRENCY,
    )

    # Total leads
    total_leads = db.scalar(
        select(func.count(Lead.id)).where(*filters)
    ) or 0

    # Count leads by status
    statement = (
        select(
            Lead.status,
            func.count(Lead.id).label("count"),
        )
        .where(*filters)
        .group_by(Lead.status)
    )

    status_rows = db.execute(statement).all()

    status_counts = {
        status: 0 for status in LEAD_STATUSES
    }

    for row in status_rows:
        status_counts[row.status] = row.count

    status_breakdown = [
        LeadStatusCount(
            status=status,
            count=count,
        )
        for status, count in status_counts.items()
    ]

    won_leads = status_counts["won"]
    lost_leads = status_counts["lost"]

    # Conversion rate = won leads / total leads * 100
    if total_leads > 0:
        conversion_rate = (
            Decimal(won_leads)
            / Decimal(total_leads)
            * Decimal("100")
        ).quantize(Decimal("0.01"))
    else:
        conversion_rate = Decimal("0.00")

    return LeadAnalytics(
        total_leads=total_leads,
        status_breakdown=status_breakdown,
        conversion_rate=conversion_rate,
        won_leads=won_leads,
        lost_leads=lost_leads,
    )


# --------------------------------------------------
# 4. SALES PIPELINE ANALYTICS
# --------------------------------------------------

def calculate_pipeline_analytics(
    db: Session,
    start_datetime: datetime,
    end_datetime: datetime,
) -> PipelineAnalytics:
    """
    Calculates the estimated value of open opportunities.

    Won and lost leads are excluded from the open pipeline.
    These figures represent estimates, not actual revenue.
    """

    statement = select(
        func.coalesce(
            func.sum(Lead.estimated_min_price),
            0,
        ),
        func.coalesce(
            func.sum(Lead.estimated_max_price),
            0,
        ),
    ).where(
        Lead.created_at >= start_datetime,
        Lead.created_at < end_datetime,
        Lead.currency == BASE_CURRENCY,
        Lead.status.in_(OPEN_STATUSES),
    )

    result = db.execute(statement).one()

    minimum_value = to_decimal(result[0])
    maximum_value = to_decimal(result[1])

    return PipelineAnalytics(
        currency=BASE_CURRENCY,
        estimated_min_value=minimum_value,
        estimated_max_value=maximum_value,
    )


# --------------------------------------------------
# 5. PACKAGE PERFORMANCE ANALYTICS
# --------------------------------------------------

def calculate_package_performance(
    db: Session,
    start_datetime: datetime,
    end_datetime: datetime,
) -> list[PackagePerformance]:
    """
    Groups customer leads by their selected package.

    Also includes unassigned leads.
    """

    statement = (
        select(
            Package.id.label("package_id"),
            Package.name.label("package_name"),

            func.count(Lead.id).label("total_leads"),

            func.sum(
                case(
                    (Lead.status == "won", 1),
                    else_=0,
                )
            ).label("won_leads"),

            func.coalesce(
                func.sum(Lead.estimated_min_price),
                0,
            ).label("estimated_min_value"),

            func.coalesce(
                func.sum(Lead.estimated_max_price),
                0,
            ).label("estimated_max_value"),
        )
        .select_from(Lead)
        .outerjoin(
            Package,
            Lead.package_id == Package.id,
        )
        .where(
            Lead.created_at >= start_datetime,
            Lead.created_at < end_datetime,
            Lead.currency == BASE_CURRENCY,
        )
        .group_by(
            Package.id,
            Package.name,
        )
        .order_by(
            Package.name.asc().nulls_last()
        )
    )

    rows = db.execute(statement).all()

    performance = []

    for row in rows:

        performance.append(
            PackagePerformance(
                package_id=row.package_id,
                package_name=row.package_name or "Unassigned",
                total_leads=row.total_leads,
                won_leads=row.won_leads or 0,
                estimated_min_value=to_decimal(
                    row.estimated_min_value
                ),
                estimated_max_value=to_decimal(
                    row.estimated_max_value
                ),
            )
        )

    return performance


# --------------------------------------------------
# 6. COMPLETE ANALYTICS DASHBOARD
# --------------------------------------------------

def get_analytics_dashboard(
    db: Session,
    filters: AnalyticsFilter,
) -> AnalyticsDashboard:
    """
    Generates the complete agency analytics dashboard.

    Combines lead statistics, pipeline value
    and package performance.
    """

    start_datetime, end_datetime = get_date_range(filters)

    # Calculate individual analytics
    lead_analytics = calculate_lead_analytics(
        db,
        start_datetime,
        end_datetime,
    )

    pipeline_analytics = calculate_pipeline_analytics(
        db,
        start_datetime,
        end_datetime,
    )

    package_performance = calculate_package_performance(
        db,
        start_datetime,
        end_datetime,
    )

    # Return validated dashboard response
    return AnalyticsDashboard(
        generated_at=datetime.now(timezone.utc),
        period_start=filters.start_date,
        period_end=filters.end_date,
        leads=lead_analytics,
        pipeline=pipeline_analytics,
        package_performance=package_performance,
    )
