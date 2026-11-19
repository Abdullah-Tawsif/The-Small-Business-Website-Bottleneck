
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from main import app
from database.database import SessionLocal
from models.lead import Lead


@pytest.fixture
def client():
    """Create a test HTTP client."""
    with TestClient(app) as test_client:
        yield test_client


def valid_lead_data():
    """Generate valid customer inquiry data."""

    return {
        "contact_name": "Rahim Uddin",
        "business_name": "Rahim Fashion",
        "email": f"test-{uuid.uuid4().hex}@example.com",
        "phone": "+8801712345678",
        "business_type": "Clothing Store",
        "project_description": (
            "We need an ecommerce website "
            "to sell clothing products online."
        ),
        "required_pages": [
            "Home",
            "Products",
            "About",
            "Contact"
        ],
        "required_features": [
            "Shopping Cart",
            "Online Payment"
        ],
        "preferred_timeline": "4-6 weeks",
        "budget_min": "20000.00",
        "budget_max": "35000.00",
        "currency": "BDT",
        "package_id": None
    }


# --------------------------------------------------
# TEST 1: SUCCESSFUL LEAD CREATION
# --------------------------------------------------

def test_create_lead_and_save_to_database(client):

    data = valid_lead_data()
    lead_id = None

    try:
        response = client.post(
            "/api/leads/",
            json=data
        )

        assert response.status_code == 201

        result = response.json()

        assert result["business_name"] == "Rahim Fashion"
        assert result["email"] == data["email"]
        assert result["status"] == "new"

        lead_id = result["id"]

        # Verify PostgreSQL persistence
        with SessionLocal() as db:

            saved_lead = db.get(Lead, lead_id)

            assert saved_lead is not None
            assert saved_lead.email == data["email"]
            assert saved_lead.status == "new"

    finally:
        # Remove test record after verification
        if lead_id is not None:
            with SessionLocal() as db:
                saved_lead = db.get(Lead, lead_id)

                if saved_lead is not None:
                    db.delete(saved_lead)
                    db.commit()


# --------------------------------------------------
# TEST 2: INVALID EMAIL
# --------------------------------------------------

def test_reject_invalid_email(client):

    data = valid_lead_data()
    data["email"] = "not-an-email"

    response = client.post(
        "/api/leads/",
        json=data
    )

    assert response.status_code == 422


# --------------------------------------------------
# TEST 3: INVALID BUDGET
# --------------------------------------------------

def test_reject_invalid_budget(client):

    data = valid_lead_data()

    data["budget_min"] = "50000"
    data["budget_max"] = "20000"

    response = client.post(
        "/api/leads/",
        json=data
    )

    assert response.status_code == 422


# --------------------------------------------------
# TEST 4: NONEXISTENT PACKAGE
# --------------------------------------------------

def test_reject_nonexistent_package(client):

    data = valid_lead_data()

    data["package_id"] = 2147483647

    response = client.post(
        "/api/leads/",
        json=data
    )

    assert response.status_code == 404
