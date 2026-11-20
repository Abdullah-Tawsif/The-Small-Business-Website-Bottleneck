
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

# SQLite uses JSON; PostgreSQL uses native JSONB.
LEAD_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Lead(Base):
    """
    Represents a potential customer interested
    in purchasing website development services.
    """

    __tablename__ = "leads"

    # Database constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL "
            "OR budget_max >= budget_min",
            name="ck_leads_budget_range",
        ),
        CheckConstraint(
            "estimated_min_price IS NULL "
            "OR estimated_max_price IS NULL "
            "OR estimated_max_price >= estimated_min_price",
            name="ck_leads_estimated_price_range",
        ),
        CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', "
            "'proposal_sent', 'won', 'lost')",
            name="ck_leads_status",
        ),
        Index("ix_leads_created_at_id", "created_at", "id"),
        Index("ix_leads_status_created_at", "status", "created_at"),
        Index("ix_leads_email", "email"),
    )

    # 1. PRIMARY KEY
    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    # 2. CUSTOMER INFORMATION
    contact_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    business_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    business_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 3. PROJECT REQUIREMENTS
    project_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    required_pages: Mapped[list[str]] = mapped_column(
        LEAD_JSON_TYPE,
        default=list,
        nullable=False,
    )

    required_features: Mapped[list[str]] = mapped_column(
        LEAD_JSON_TYPE,
        default=list,
        nullable=False,
    )

    preferred_timeline: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # 4. CUSTOMER BUDGET
    budget_min: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    budget_max: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # 5. AI-GENERATED SCOPE AND ESTIMATE
    ai_scope_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    estimated_min_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    estimated_max_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # Recommended website package
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 6. LEAD STATUS
    status: Mapped[str] = mapped_column(
        String(30),
        default="new",
        nullable=False,
        index=True,
    )

    # 7. CURRENCY
    currency: Mapped[str] = mapped_column(
        String(3),
        default="BDT",
        nullable=False,
    )

    # 8. TIMESTAMPS
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

    # 9. OBJECT REPRESENTATION
    def __repr__(self) -> str:
        return (
            f"<Lead("
            f"id={self.id}, "
            f"business_name='{self.business_name}', "
            f"status='{self.status}'"
            f")>"
        )
