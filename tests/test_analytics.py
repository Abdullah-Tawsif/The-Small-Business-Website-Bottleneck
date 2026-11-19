"""Unit tests for the analytics service.

These tests mock SQLAlchemy session results so they do not connect to, read
from, or write to the application's database.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import services.analytics_service as analytics_service
from schemas.analytics import (
    AnalyticsFilter,
    LeadAnalytics,
    PipelineAnalytics,
    PackagePerformance,
)


BANGLADESH_TIMEZONE = ZoneInfo("Asia/Dhaka")
START_DATETIME = datetime(2026, 1, 1, 0, 0, tzinfo=BANGLADESH_TIMEZONE)
END_DATETIME = datetime(2026, 2, 1, 0, 0, tzinfo=BANGLADESH_TIMEZONE)

EXPECTED_STATUSES = {
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
    "won",
    "lost",
}


def _row(status: str, count: int):
    """Create the row-like object returned by the grouped status query."""
    return SimpleNamespace(status=status, count=count)


def _assert_common_sql_filters(statement, start_datetime, end_datetime):
    """Assert that an analytics SQL statement carries its date/currency filters."""
    compiled = statement.compile()
    sql = str(compiled)
    params = compiled.params

    # The service uses an inclusive start and exclusive end timestamp.
    assert ">=" in sql
    assert " < " in sql
    assert start_datetime in params.values()
    assert end_datetime in params.values()
    assert "BDT" in params.values()


@pytest.fixture

def date_range():
    return START_DATETIME, END_DATETIME


# ---------------------------------------------------------------------------
# Date filter and timezone handling
# ---------------------------------------------------------------------------


def test_get_date_range_uses_bangladesh_timezone_and_inclusive_end_date():
    filters = AnalyticsFilter(
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 12),
    )

    start_datetime, end_datetime = analytics_service.get_date_range(filters)

    assert start_datetime == datetime(
        2026, 1, 10, 0, 0, tzinfo=BANGLADESH_TIMEZONE
    )
    # End date is inclusive, so the query's exclusive upper bound is midnight
    # at the start of the following Bangladesh calendar day.
    assert end_datetime == datetime(
        2026, 1, 13, 0, 0, tzinfo=BANGLADESH_TIMEZONE
    )
    assert start_datetime.tzinfo == BANGLADESH_TIMEZONE
    assert end_datetime.tzinfo == BANGLADESH_TIMEZONE


def test_get_date_range_for_single_day_covers_exactly_one_day():
    filters = AnalyticsFilter(
        start_date=date(2026, 4, 5),
        end_date=date(2026, 4, 5),
    )

    start_datetime, end_datetime = analytics_service.get_date_range(filters)

    assert end_datetime - start_datetime == timedelta(days=1)
    assert start_datetime.time() == time.min
    assert end_datetime.date() == date(2026, 4, 6)


def test_analytics_filter_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError, match="End date cannot be earlier"):
        AnalyticsFilter(
            start_date=date(2026, 5, 2),
            end_date=date(2026, 5, 1),
        )


# ---------------------------------------------------------------------------
# Lead totals, status distribution, and conversion rate
# ---------------------------------------------------------------------------


def test_calculate_lead_analytics_returns_total_and_all_status_counts(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.scalar.return_value = 10
    db.execute.return_value.all.return_value = [
        _row("new", 2),
        _row("contacted", 1),
        _row("qualified", 2),
        _row("proposal_sent", 1),
        _row("won", 3),
        _row("lost", 1),
    ]

    result = analytics_service.calculate_lead_analytics(
        db, start_datetime, end_datetime
    )

    assert isinstance(result, LeadAnalytics)
    assert result.total_leads == 10
    assert result.won_leads == 3
    assert result.lost_leads == 1
    assert result.conversion_rate == Decimal("30.00")
    assert {item.status for item in result.status_breakdown} == EXPECTED_STATUSES
    assert {
        item.status: item.count for item in result.status_breakdown
    } == {
        "new": 2,
        "contacted": 1,
        "qualified": 2,
        "proposal_sent": 1,
        "won": 3,
        "lost": 1,
    }


def test_calculate_lead_analytics_includes_zero_count_statuses(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.scalar.return_value = 2
    db.execute.return_value.all.return_value = [
        _row("new", 1),
        _row("won", 1),
    ]

    result = analytics_service.calculate_lead_analytics(
        db, start_datetime, end_datetime
    )

    counts = {item.status: item.count for item in result.status_breakdown}
    assert counts["new"] == 1
    assert counts["won"] == 1
    assert counts["contacted"] == 0
    assert counts["qualified"] == 0
    assert counts["proposal_sent"] == 0
    assert counts["lost"] == 0


def test_conversion_rate_is_rounded_to_two_decimal_places(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.scalar.return_value = 6
    db.execute.return_value.all.return_value = [
        _row("new", 1),
        _row("contacted", 1),
        _row("qualified", 1),
        _row("proposal_sent", 1),
        _row("won", 2),
    ]

    result = analytics_service.calculate_lead_analytics(
        db, start_datetime, end_datetime
    )

    assert result.conversion_rate == Decimal("33.33")


def test_zero_leads_returns_zero_conversion_and_zero_status_counts(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []

    result = analytics_service.calculate_lead_analytics(
        db, start_datetime, end_datetime
    )

    assert result.total_leads == 0
    assert result.won_leads == 0
    assert result.lost_leads == 0
    assert result.conversion_rate == Decimal("0.00")
    assert len(result.status_breakdown) == len(EXPECTED_STATUSES)
    assert all(item.count == 0 for item in result.status_breakdown)


def test_lead_analytics_applies_date_and_bdt_filters(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []

    analytics_service.calculate_lead_analytics(
        db, start_datetime, end_datetime
    )

    total_query = db.scalar.call_args.args[0]
    status_query = db.execute.call_args.args[0]
    _assert_common_sql_filters(total_query, start_datetime, end_datetime)
    _assert_common_sql_filters(status_query, start_datetime, end_datetime)


# ---------------------------------------------------------------------------
# Open sales pipeline value
# ---------------------------------------------------------------------------


def test_calculate_pipeline_analytics_sums_minimum_and_maximum_values(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.one.return_value = (
        Decimal("125000.50"),
        Decimal("210000.75"),
    )

    result = analytics_service.calculate_pipeline_analytics(
        db, start_datetime, end_datetime
    )

    assert isinstance(result, PipelineAnalytics)
    assert result.currency == "BDT"
    assert result.estimated_min_value == Decimal("125000.50")
    assert result.estimated_max_value == Decimal("210000.75")


def test_pipeline_analytics_converts_null_aggregate_values_to_zero(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    # Defensive test for a database result where aggregate values are NULL.
    db.execute.return_value.one.return_value = (None, None)

    result = analytics_service.calculate_pipeline_analytics(
        db, start_datetime, end_datetime
    )

    assert result.estimated_min_value == Decimal("0.00")
    assert result.estimated_max_value == Decimal("0.00")


def test_pipeline_query_filters_to_open_statuses_and_date_range(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.one.return_value = (0, 0)

    analytics_service.calculate_pipeline_analytics(
        db, start_datetime, end_datetime
    )

    statement = db.execute.call_args.args[0]
    _assert_common_sql_filters(statement, start_datetime, end_datetime)

    compiled = statement.compile()
    sql = str(compiled)
    assert "status IN" in sql or "status in" in sql.lower()
    assert set(analytics_service.OPEN_STATUSES).issubset(
        {value for value in compiled.params.values() if isinstance(value, str)}
        | {
            item
            for value in compiled.params.values()
            if isinstance(value, (tuple, list))
            for item in value
        }
    )


def test_empty_pipeline_returns_zero_values(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.one.return_value = (Decimal("0"), Decimal("0"))

    result = analytics_service.calculate_pipeline_analytics(
        db, start_datetime, end_datetime
    )

    assert result.estimated_min_value == Decimal("0")
    assert result.estimated_max_value == Decimal("0")


# ---------------------------------------------------------------------------
# Package performance and unassigned leads
# ---------------------------------------------------------------------------


def test_calculate_package_performance_returns_package_and_unassigned_groups(
    date_range,
):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(
            package_id=2,
            package_name="Business",
            total_leads=3,
            won_leads=1,
            estimated_min_value=Decimal("90000.00"),
            estimated_max_value=Decimal("150000.00"),
        ),
        SimpleNamespace(
            package_id=1,
            package_name="Starter",
            total_leads=5,
            won_leads=2,
            estimated_min_value=Decimal("50000.00"),
            estimated_max_value=Decimal("80000.00"),
        ),
        SimpleNamespace(
            package_id=None,
            package_name=None,
            total_leads=2,
            won_leads=0,
            estimated_min_value=Decimal("10000.00"),
            estimated_max_value=Decimal("20000.00"),
        ),
    ]

    result = analytics_service.calculate_package_performance(
        db, start_datetime, end_datetime
    )

    assert len(result) == 3
    assert all(isinstance(item, PackagePerformance) for item in result)
    # The service orders named packages alphabetically, with unassigned last.
    assert [item.package_name for item in result] == [
        "Business", "Starter", "Unassigned"
    ]
    assert result[0].package_id == 2
    assert result[0].total_leads == 3
    assert result[0].won_leads == 1
    assert result[0].estimated_min_value == Decimal("90000.00")
    assert result[0].estimated_max_value == Decimal("150000.00")

    assert result[1].package_id == 1
    assert result[1].total_leads == 5
    assert result[1].won_leads == 2
    assert result[1].estimated_min_value == Decimal("50000.00")
    assert result[1].estimated_max_value == Decimal("80000.00")

    assert result[2].package_id is None
    assert result[2].package_name == "Unassigned"
    assert result[2].total_leads == 2
    assert result[2].won_leads == 0


def test_package_performance_handles_null_won_count_and_numeric_values(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(
            package_id=7,
            package_name="Basic",
            total_leads=1,
            won_leads=None,
            estimated_min_value=1000,
            estimated_max_value=2000,
        )
    ]

    result = analytics_service.calculate_package_performance(
        db, start_datetime, end_datetime
    )

    assert result[0].won_leads == 0
    assert result[0].estimated_min_value == Decimal("1000")
    assert result[0].estimated_max_value == Decimal("2000")


def test_package_performance_returns_empty_list_when_no_leads(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.all.return_value = []

    result = analytics_service.calculate_package_performance(
        db, start_datetime, end_datetime
    )

    assert result == []


def test_package_performance_query_applies_date_and_bdt_filters(date_range):
    start_datetime, end_datetime = date_range
    db = Mock()
    db.execute.return_value.all.return_value = []

    analytics_service.calculate_package_performance(
        db, start_datetime, end_datetime
    )

    statement = db.execute.call_args.args[0]
    _assert_common_sql_filters(statement, start_datetime, end_datetime)
    # The left outer join is important: package-less leads must remain visible.
    assert "LEFT OUTER JOIN" in str(statement.compile()).upper()


# ---------------------------------------------------------------------------
# Complete dashboard orchestration
# ---------------------------------------------------------------------------


def test_get_analytics_dashboard_passes_date_range_to_all_calculations(monkeypatch):
    filters = AnalyticsFilter(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )
    expected_start, expected_end = analytics_service.get_date_range(filters)

    leads = LeadAnalytics(
        total_leads=0,
        status_breakdown=[],
        conversion_rate=Decimal("0.00"),
        won_leads=0,
        lost_leads=0,
    )
    pipeline = PipelineAnalytics(
        currency="BDT",
        estimated_min_value=Decimal("0"),
        estimated_max_value=Decimal("0"),
    )

    lead_calculator = Mock(return_value=leads)
    pipeline_calculator = Mock(return_value=pipeline)
    package_calculator = Mock(return_value=[])

    monkeypatch.setattr(
        analytics_service, "calculate_lead_analytics", lead_calculator
    )
    monkeypatch.setattr(
        analytics_service, "calculate_pipeline_analytics", pipeline_calculator
    )
    monkeypatch.setattr(
        analytics_service, "calculate_package_performance", package_calculator
    )

    db = Mock()
    dashboard = analytics_service.get_analytics_dashboard(db, filters)

    assert dashboard.period_start == date(2026, 7, 1)
    assert dashboard.period_end == date(2026, 7, 31)
    assert dashboard.leads == leads
    assert dashboard.pipeline == pipeline
    assert dashboard.package_performance == []

    expected_call = ((db, expected_start, expected_end),)
    lead_calculator.assert_called_once_with(*expected_call[0])
    pipeline_calculator.assert_called_once_with(*expected_call[0])
    package_calculator.assert_called_once_with(*expected_call[0])
    assert dashboard.generated_at.tzinfo is not None
