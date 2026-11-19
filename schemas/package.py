
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


# --------------------------------------------------
# 1. COMMON PACKAGE FIELDS
# --------------------------------------------------

class PackageBase(BaseModel):

    name: str = Field(
        min_length=1,
        max_length=100,
    )

    slug: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )

    description: str = Field(
        min_length=1,
    )

    min_price: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    max_price: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    currency: str = Field(
        default="BDT",
        pattern=r"^[A-Z]{3}$",
    )

    features: list[str] = Field(
        default_factory=list,
    )

    is_active: bool = True

    display_order: int = Field(
        default=0,
        ge=0,
    )

    @model_validator(mode="after")
    def validate_price_range(self):

        if self.max_price < self.min_price:
            raise ValueError(
                "Maximum price cannot be lower than minimum price."
            )

        return self


# --------------------------------------------------
# 2. PACKAGE CREATION SCHEMA
# --------------------------------------------------

class PackageCreate(PackageBase):
    """
    Validates data when creating a new package.
    """

    pass


# --------------------------------------------------
# 3. PACKAGE UPDATE SCHEMA
# --------------------------------------------------

class PackageUpdate(BaseModel):
    """
    Allows partial updates to an existing package.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )

    description: str | None = Field(
        default=None,
        min_length=1,
    )

    min_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    max_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    currency: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
    )

    features: list[str] | None = None

    is_active: bool | None = None

    display_order: int | None = Field(
        default=None,
        ge=0,
    )

    @model_validator(mode="after")
    def validate_price_range(self):

        if (
            self.min_price is not None
            and self.max_price is not None
            and self.max_price < self.min_price
        ):
            raise ValueError(
                "Maximum price cannot be lower than minimum price."
            )

        return self


# --------------------------------------------------
# 4. PACKAGE RESPONSE SCHEMA
# --------------------------------------------------

class PackageResponse(PackageBase):
    """
    Defines the package information returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    created_at: datetime

    updated_at: datetime
