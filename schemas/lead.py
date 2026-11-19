
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --------------------------------------------------
# 1. ANALYTICS DATE FILTER
# --------------------------------------------------

class AnalyticsFilter(BaseModel):
    """
    Defines the date range for analytics queries.
    """

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self):

        if self.end_date < self.start_date:
            raise ValueError(
                "End date cannot be earlier than start date."
            )

        return self


# --------------------------------------------------
# 2. LEAD STATUS ANALYTICS
# --------------------------------------------------

LeadStatus = Literal[
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
    "won",
    "lost",
]


class LeadStatusCount(BaseModel):
    """
    Number of leads belonging to each status.
    """

    status: LeadStatus

    count: int = Field(
        ge=0,
    )


# --------------------------------------------------
# 3. PACKAGE PERFORMANCE
# --------------------------------------------------

class PackagePerformance(BaseModel):
    """
    Analytics for individual website packages.
    """

    package_id: int | None

    package_name: str

    total_leads: int = Field(
        ge=0,
    )

    won_leads: int = Field(
        ge=0,
    )

    estimated_min_value: Decimal = Field(
        ge=0,
    )

    estimated_max_value: Decimal = Field(
        ge=0,
    )

    @model_validator(mode="after")
    def validate_performance(self):

        if self.won_leads > self.total_leads:
            raise ValueError(
                "Won leads cannot exceed total leads."
            )

        if self.estimated_max_value < self.estimated_min_value:
            raise ValueError(
                "Maximum estimated value cannot be lower "
                "than minimum estimated value."
            )

        return self


# --------------------------------------------------
# 4. LEAD ANALYTICS SUMMARY
# --------------------------------------------------

class LeadAnalytics(BaseModel):
    """
    Overall statistics about customer leads.
    """

    total_leads: int = Field(
        ge=0,
    )

    status_breakdown: list[LeadStatusCount] = Field(
        default_factory=list,
    )

    conversion_rate: Decimal = Field(
        ge=0,
        le=100,
    )

    won_leads: int = Field(
        ge=0,
    )

    lost_leads: int = Field(
        ge=0,
    )

    @model_validator(mode="after")
    def validate_lead_statistics(self):

        if self.won_leads + self.lost_leads > self.total_leads:
            raise ValueError(
                "Won and lost leads cannot exceed total leads."
            )

        return self


# --------------------------------------------------
# 5. ESTIMATED PIPELINE VALUE
# --------------------------------------------------

class PipelineAnalytics(BaseModel):
    """
    Tracks the estimated value of customer opportunities.
    These figures are estimates, not actual revenue.
    """

    currency: str = Field(
        default="BDT",
        pattern=r"^[A-Z]{3}$",
    )

    estimated_min_value: Decimal = Field(
        ge=0,
    )

    estimated_max_value: Decimal = Field(
        ge=0,
    )

    @model_validator(mode="after")
    def validate_pipeline_values(self):

        if self.estimated_max_value < self.estimated_min_value:
            raise ValueError(
                "Maximum pipeline value cannot be lower "
                "than minimum pipeline value."
            )

        return self


# --------------------------------------------------
# 6. COMPLETE DASHBOARD RESPONSE
# --------------------------------------------------

class AnalyticsDashboard(BaseModel):
    """
    Complete analytics response for the admin dashboard.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    generated_at: datetime

    period_start: date

    period_end: date

    leads: LeadAnalytics

    pipeline: PipelineAnalytics

    package_performance: list[PackagePerformance] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_dashboard_period(self):

        if self.period_end < self.period_start:
            raise ValueError(
                "Dashboard end date cannot precede start date."
            )

        return self
