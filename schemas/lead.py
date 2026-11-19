
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


# --------------------------------------------------
# 1. ALLOWED LEAD STATUSES
# --------------------------------------------------

LeadStatus = Literal[
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
    "won",
    "lost",
]


# --------------------------------------------------
# 2. COMMON LEAD INPUT FIELDS
# --------------------------------------------------

class LeadBase(BaseModel):
    """
    Common customer and project information.
    """

    contact_name: str = Field(
        min_length=2,
        max_length=150,
    )

    business_name: str = Field(
        min_length=2,
        max_length=200,
    )

    email: EmailStr

    phone: str | None = Field(
        default=None,
        max_length=30,
    )

    business_type: str = Field(
        min_length=2,
        max_length=100,
    )

    project_description: str = Field(
        min_length=10,
        max_length=5000,
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

    package_id: int | None = Field(
        default=None,
        gt=0,
    )

    currency: str = Field(
        default="BDT",
        pattern=r"^[A-Z]{3}$",
    )

    # Clean and validate lists
    @field_validator(
        "required_pages",
        "required_features",
    )
    @classmethod
    def clean_list_items(cls, items: list[str]) -> list[str]:

        cleaned = [item.strip() for item in items]

        if any(not item for item in cleaned):
            raise ValueError(
                "List items cannot be empty."
            )

        if len(set(item.casefold() for item in cleaned)) != len(cleaned):
            raise ValueError(
                "Duplicate items are not allowed."
            )

        return cleaned

    # Validate budget range
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


# --------------------------------------------------
# 3. CREATE LEAD SCHEMA
# --------------------------------------------------

class LeadCreate(LeadBase):
    """
    Validates a new customer inquiry.

    Customers cannot directly submit internal fields
    such as lead status or AI-generated estimates.
    """

    model_config = ConfigDict(
        extra="forbid",
    )


# --------------------------------------------------
# 4. LEAD RESPONSE SCHEMA
# --------------------------------------------------

class LeadResponse(BaseModel):
    """
    Defines information returned to the API client.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    contact_name: str

    business_name: str

    email: EmailStr

    phone: str | None

    business_type: str

    project_description: str

    required_pages: list[str]

    required_features: list[str]

    preferred_timeline: str | None

    budget_min: Decimal | None

    budget_max: Decimal | None

    ai_scope_summary: str | None

    estimated_min_price: Decimal | None

    estimated_max_price: Decimal | None

    package_id: int | None

    status: LeadStatus

    currency: str

    created_at: datetime

    updated_at: datetime
