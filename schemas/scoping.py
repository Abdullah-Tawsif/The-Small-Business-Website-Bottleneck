
"""Request and response schemas for AI-powered website project scoping."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScopingRequest(BaseModel):
    """Customer input for creating or continuing a scoping session."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    session_id: UUID | None = None

    message: str = Field(
        min_length=3,
        max_length=4000,
    )

    business_name: str | None = Field(
        default=None,
        max_length=200,
    )

    business_type: str | None = Field(
        default=None,
        max_length=100,
    )

    project_description: str | None = Field(
        default=None,
        max_length=5000,
    )

    goals: list[str] = Field(
        default_factory=list,
        max_length=12,
    )

    current_website: str | None = Field(
        default=None,
        max_length=500,
    )

    required_pages: list[str] = Field(
        default_factory=list,
        max_length=30,
    )

    required_features: list[str] = Field(
        default_factory=list,
        max_length=50,
    )

    preferred_timeline: str | None = Field(
        default=None,
        max_length=100,
    )

    budget_min: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    budget_max: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    @model_validator(mode="after")
    def validate_budget(self):
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_max < self.budget_min
        ):
            raise ValueError(
                "Maximum budget cannot be lower than minimum budget."
            )

        return self


class ScopingResponse(BaseModel):
    """Structured AI-generated website scope."""

    session_id: UUID

    scope_summary: str

    required_pages: list[str] = Field(
        default_factory=list,
    )

    required_features: list[str] = Field(
        default_factory=list,
    )

    clarifying_questions: list[str] = Field(
        default_factory=list,
    )

    recommended_package_id: int | None = None
