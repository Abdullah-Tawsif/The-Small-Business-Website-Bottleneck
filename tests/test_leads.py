
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import database.database as database_module
from config.settings import get_settings
from database.database import Base, get_db
from main import app
from models.lead import Lead
from asgi_client import SyncASGIClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Run lead API tests with a database confined to pytest's temp folder."""
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'lead-api-tests.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    test_sessions = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(test_engine)
    with test_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        current_head = ScriptDirectory(
            str(Path(__file__).resolve().parents[1] / "migrations")
        ).get_current_head()
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
            {"version": current_head},
        )
    monkeypatch.setattr(database_module, "engine", test_engine)
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "isolated-lead-api-tests-secret-at-least-32-bytes",
    )
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "")
    get_settings.cache_clear()

    def override_get_db():
        with test_sessions() as db:
            yield db

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    try:
        with SyncASGIClient(app) as test_client:
            yield test_client, test_sessions
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        get_settings.cache_clear()
        test_engine.dispose()


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

    test_client, test_sessions = client
    data = valid_lead_data()
    lead_id = None

    try:
        response = test_client.post(
            "/api/leads/",
            json=data
        )

        assert response.status_code == 201

        result = response.json()

        assert result["business_name"] == "Rahim Fashion"
        assert result["email"] == data["email"]
        assert result["status"] == "new"

        lead_id = result["id"]

        # Verify persistence in the disposable SQLite database.
        with test_sessions() as db:

            saved_lead = db.get(Lead, lead_id)

            assert saved_lead is not None
            assert saved_lead.email == data["email"]
            assert saved_lead.status == "new"

    finally:
        # Remove test record after verification
        if lead_id is not None:
            with test_sessions() as db:
                saved_lead = db.get(Lead, lead_id)

                if saved_lead is not None:
                    db.delete(saved_lead)
                    db.commit()


# --------------------------------------------------
# TEST 2: INVALID EMAIL
# --------------------------------------------------

def test_reject_invalid_email(client):

    test_client, _ = client
    data = valid_lead_data()
    data["email"] = "not-an-email"

    response = test_client.post(
        "/api/leads/",
        json=data
    )

    assert response.status_code == 422


# --------------------------------------------------
# TEST 3: INVALID BUDGET
# --------------------------------------------------

def test_reject_invalid_budget(client):

    test_client, _ = client
    data = valid_lead_data()

    data["budget_min"] = "50000"
    data["budget_max"] = "20000"

    response = test_client.post(
        "/api/leads/",
        json=data
    )

    assert response.status_code == 422


# --------------------------------------------------
# TEST 4: NONEXISTENT PACKAGE
# --------------------------------------------------

def test_reject_nonexistent_package(client):

    test_client, _ = client
    data = valid_lead_data()

    data["package_id"] = 2147483647

    response = test_client.post(
        "/api/leads/",
        json=data
    )

    assert response.status_code == 404
