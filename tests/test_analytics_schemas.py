"""Unit tests for the Pydantic analytics response schemas.

These tests validate the input/output contracts in ``schemas/analytics.py``.
They do not connect to a database or modify application data.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.analytics import (
    AnalyticsDashboard,
    AnalyticsFilter,
    LeadAnalytics,
    LeadStatusCount,
    PackagePerformance,
    PipelineAnalytics,
)


# ---------------------------------------------------------------------------
# Shared valid payloads
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_lead_analytics():
    return {
        "total_leads": 10,
        "status_breakdown": [
            {"status": "new", "count": 4},
            {"status": "contacted", "count": 2},
            {"status": "qualified", "count": 1},
            {"status": "proposal_sent", "count": 1},
            {"status": "won", "count": 1},
            {"status": "lost", "count": 1},
        ],
        "conversion_rate": Decimal("10.00"),
        "won_leads": 1,
        "lost_leads": 1,
    }


@pytest.fixture
def valid_pipeline_analytics():
    return {
        "currency": "BDT",
        "estimated_min_value": Decimal("12000.00"),
        "estimated_max_value": Decimal("25000.00"),
    }


# ---------------------------------------------------------------------------
# AnalyticsFilter
# ---------------------------------------------------------------------------


def test_analytics_filter_accepts_valid_date_range():
    result = AnalyticsFilter(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 1, 31)


def test_analytics_filter_allows_single_day_period():
    result = AnalyticsFilter(
        start_date=date(2026, 5, 10),
        end_date=date(2026, 5, 10),
    )

    assert result.start_date == result.end_date


def test_analytics_filter_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError, match="End date cannot be earlier"):
        AnalyticsFilter(
            start_date=date(2026, 5, 11),
            end_date=date(2026, 5, 10),
        )


# ---------------------------------------------------------------------------
# LeadStatusCount
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    ["new", "contacted", "qualified", "proposal_sent", "won", "lost"],
)
def test_lead_status_count_accepts_each_supported_status(status):
    result = LeadStatusCount(status=status, count=0)

    assert result.status == status
    assert result.count == 0


def test_lead_status_count_rejects_unknown_status():
    with pytest.raises(ValidationError):
        LeadStatusCount(status="pending", count=1)


def test_lead_status_count_rejects_negative_count():
    with pytest.raises(ValidationError):
        LeadStatusCount(status="new", count=-1)


# ---------------------------------------------------------------------------
# PackagePerformance
# ---------------------------------------------------------------------------


def test_package_performance_accepts_regular_package():
    result = PackagePerformance(
        package_id=3,
        package_name="Growth",
        total_leads=8,
        won_leads=2,
        estimated_min_value=Decimal("15000.00"),
        estimated_max_value=Decimal("30000.00"),
    )

    assert result.package_id == 3
    assert result.package_name == "Growth"
    assert result.total_leads == 8
    assert result.won_leads == 2


def test_package_performance_accepts_unassigned_package():
    result = PackagePerformance(
        package_id=None,
        package_name="Unassigned",
        total_leads=2,
        won_leads=0,
        estimated_min_value=Decimal("0.00"),
        estimated_max_value=Decimal("0.00"),
    )

    assert result.package_id is None
    assert result.package_name == "Unassigned"


def test_package_performance_allows_won_leads_equal_to_total():
    result = PackagePerformance(
        package_id=1,
        package_name="Starter",
        total_leads=3,
        won_leads=3,
        estimated_min_value=Decimal("1000"),
        estimated_max_value=Decimal("2000"),
    )

    assert result.won_leads == result.total_leads


def test_package_performance_rejects_won_leads_above_total():
    with pytest.raises(ValidationError, match="Won leads cannot exceed total"):
        PackagePerformance(
            package_id=1,
            package_name="Starter",
            total_leads=2,
            won_leads=3,
            estimated_min_value=Decimal("1000"),
            estimated_max_value=Decimal("2000"),
        )


def test_package_performance_rejects_maximum_below_minimum():
    with pytest.raises(ValidationError, match="Maximum estimated value"):
        PackagePerformance(
            package_id=1,
            package_name="Starter",
            total_leads=2,
            won_leads=1,
            estimated_min_value=Decimal("5000"),
            estimated_max_value=Decimal("4000"),
        )


def test_package_performance_rejects_negative_estimated_value():
    with pytest.raises(ValidationError):
        PackagePerformance(
            package_id=1,
            package_name="Starter",
            total_leads=2,
            won_leads=0,
            estimated_min_value=Decimal("-1"),
            estimated_max_value=Decimal("1000"),
        )


# ---------------------------------------------------------------------------
# LeadAnalytics
# ---------------------------------------------------------------------------


def test_lead_analytics_accepts_valid_summary(valid_lead_analytics):
    result = LeadAnalytics(**valid_lead_analytics)

    assert result.total_leads == 10
    assert result.conversion_rate == Decimal("10.00")
    assert result.won_leads == 1
    assert result.lost_leads == 1
    assert len(result.status_breakdown) == 6


def test_lead_analytics_accepts_zero_lead_summary():
    result = LeadAnalytics(
        total_leads=0,
        status_breakdown=[],
        conversion_rate=Decimal("0.00"),
        won_leads=0,
        lost_leads=0,
    )

    assert result.total_leads == 0
    assert result.conversion_rate == Decimal("0.00")


def test_lead_analytics_accepts_conversion_rate_boundaries():
    zero_conversion = LeadAnalytics(
        total_leads=1,
        status_breakdown=[],
        conversion_rate=Decimal("0"),
        won_leads=0,
        lost_leads=0,
    )
    full_conversion = LeadAnalytics(
        total_leads=1,
        status_breakdown=[],
        conversion_rate=Decimal("100"),
        won_leads=1,
        lost_leads=0,
    )

    assert zero_conversion.conversion_rate == Decimal("0")
    assert full_conversion.conversion_rate == Decimal("100")


@pytest.mark.parametrize("conversion_rate", [Decimal("-0.01"), Decimal("100.01")])
def test_lead_analytics_rejects_conversion_rate_outside_zero_to_100(
    conversion_rate,
):
    with pytest.raises(ValidationError):
        LeadAnalytics(
            total_leads=1,
            status_breakdown=[],
            conversion_rate=conversion_rate,
            won_leads=0,
            lost_leads=0,
        )


def test_lead_analytics_rejects_won_and_lost_above_total():
    with pytest.raises(ValidationError, match="Won and lost leads cannot exceed"):
        LeadAnalytics(
            total_leads=3,
            status_breakdown=[],
            conversion_rate=Decimal("33.33"),
            won_leads=2,
            lost_leads=2,
        )


def test_lead_analytics_rejects_negative_total_leads():
    with pytest.raises(ValidationError):
        LeadAnalytics(
            total_leads=-1,
            status_breakdown=[],
            conversion_rate=Decimal("0"),
            won_leads=0,
            lost_leads=0,
        )


# ---------------------------------------------------------------------------
# PipelineAnalytics
# ---------------------------------------------------------------------------


def test_pipeline_analytics_defaults_currency_to_bdt():
    result = PipelineAnalytics(
        estimated_min_value=Decimal("0"),
        estimated_max_value=Decimal("0"),
    )

    assert result.currency == "BDT"


def test_pipeline_analytics_accepts_valid_range(valid_pipeline_analytics):
    result = PipelineAnalytics(**valid_pipeline_analytics)

    assert result.estimated_min_value == Decimal("12000.00")
    assert result.estimated_max_value == Decimal("25000.00")


def test_pipeline_analytics_rejects_invalid_currency_format():
    for currency in ("bdt", "US", "USDD", "12D"):
        with pytest.raises(ValidationError):
            PipelineAnalytics(
                currency=currency,
                estimated_min_value=Decimal("0"),
                estimated_max_value=Decimal("0"),
            )


def test_pipeline_analytics_rejects_maximum_below_minimum():
    with pytest.raises(ValidationError, match="Maximum pipeline value"):
        PipelineAnalytics(
            estimated_min_value=Decimal("10000"),
            estimated_max_value=Decimal("9000"),
        )


def test_pipeline_analytics_rejects_negative_minimum():
    with pytest.raises(ValidationError):
        PipelineAnalytics(
            estimated_min_value=Decimal("-1"),
            estimated_max_value=Decimal("100"),
        )


# ---------------------------------------------------------------------------
# AnalyticsDashboard
# ---------------------------------------------------------------------------


def test_analytics_dashboard_accepts_complete_payload(
    valid_lead_analytics,
    valid_pipeline_analytics,
):
    result = AnalyticsDashboard(
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        leads=valid_lead_analytics,
        pipeline=valid_pipeline_analytics,
        package_performance=[
            {
                "package_id": 1,
                "package_name": "Starter",
                "total_leads": 2,
                "won_leads": 1,
                "estimated_min_value": Decimal("3000"),
                "estimated_max_value": Decimal("6000"),
            }
        ],
    )

    assert result.period_start == date(2026, 5, 1)
    assert result.period_end == date(2026, 5, 31)
    assert len(result.package_performance) == 1


def test_analytics_dashboard_defaults_package_performance_to_empty_list(
    valid_lead_analytics,
    valid_pipeline_analytics,
):
    result = AnalyticsDashboard(
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        leads=valid_lead_analytics,
        pipeline=valid_pipeline_analytics,
    )

    assert result.package_performance == []


def test_analytics_dashboard_rejects_end_date_before_start_date(
    valid_lead_analytics,
    valid_pipeline_analytics,
):
    with pytest.raises(ValidationError, match="Dashboard end date cannot precede"):
        AnalyticsDashboard(
            generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            period_start=date(2026, 5, 2),
            period_end=date(2026, 5, 1),
            leads=valid_lead_analytics,
            pipeline=valid_pipeline_analytics,
        )
