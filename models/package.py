
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class Package(Base):
    """
    Represents a website development service package.
    """

    __tablename__ = "packages"

    # Database constraints
    __table_args__ = (
        CheckConstraint(
            "min_price >= 0",
            name="ck_packages_min_price_nonnegative",
        ),
        CheckConstraint(
            "max_price >= min_price",
            name="ck_packages_max_price_gte_min",
        ),
    )

    # Unique package identifier
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # Basic package information
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Pricing information
    min_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    max_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="BDT",
        nullable=False,
    )

    # Package features stored as PostgreSQL JSONB
    features: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    # Package availability
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Automatic timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Package("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"min_price={self.min_price}, "
            f"max_price={self.max_price}"
            f")>"
        )
