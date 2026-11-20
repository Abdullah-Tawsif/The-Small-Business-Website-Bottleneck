from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database.database import Base
from models.lead import Lead
from models.package import Package
from schemas.lead import LeadCreate
from services.lead_service import (
    PackageUnavailableError,
    create_lead,
    update_lead_status,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lead-service.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def make_lead(**overrides):
    values = {
        "contact_name": "Customer Name",
        "business_name": "Example Business",
        "email": "customer@example.com",
        "phone": "+8801712345678",
        "business_type": "Retail",
        "project_description": "We need a website to present and sell our products.",
        "required_pages": ["Home", "Products"],
        "required_features": ["Shopping Cart"],
        "preferred_timeline": "6 weeks",
        "budget_min": Decimal("10000.00"),
        "budget_max": Decimal("30000.00"),
        "package_id": None,
        "currency": "BDT",
    }
    values.update(overrides)
    return LeadCreate(**values)


def test_create_lead_persists_customer_inquiry(db_session):
    lead = create_lead(db_session, make_lead())

    saved = db_session.scalar(select(Lead).where(Lead.id == lead.id))
    assert saved is not None
    assert saved.status == "new"
    assert saved.email == "customer@example.com"
    assert saved.required_pages == ["Home", "Products"]
    assert saved.estimated_min_price is None


def test_create_lead_saves_estimate_from_active_package(db_session):
    package = Package(
        name="Starter",
        slug="starter",
        description="Starter website",
        min_price=Decimal("10000.00"),
        max_price=Decimal("15000.00"),
        currency="BDT",
        features=[],
        is_active=True,
        display_order=1,
    )
    db_session.add(package)
    db_session.commit()

    lead = create_lead(
        db_session,
        make_lead(package_id=package.id),
    )

    assert lead.package_id == package.id
    assert lead.estimated_min_price == Decimal("14000.00")
    assert lead.estimated_max_price == Decimal("22000.00")


def test_create_lead_rolls_back_when_package_is_unavailable(db_session):
    with pytest.raises(PackageUnavailableError):
        create_lead(db_session, make_lead(package_id=987654))

    assert db_session.scalar(select(Lead)) is None


def test_update_lead_status_persists_transition(db_session):
    lead = create_lead(db_session, make_lead())

    updated = update_lead_status(db_session, lead.id, "qualified")

    assert updated.status == "qualified"
    assert db_session.get(Lead, lead.id).status == "qualified"
