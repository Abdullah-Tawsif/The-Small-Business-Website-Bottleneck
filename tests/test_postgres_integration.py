"""Service-backed PostgreSQL migration and persistence checks."""

import os
import uuid
from decimal import Decimal

import pytest
import asyncio
import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.migration_safety import REPOSITORY_ROOT
from models.ai_session import AISession
from models.lead import Lead
from models.package import Package
from models.user import User
from config.settings import get_settings
from database.database import get_db
from main import app
from utils.security import create_access_token


POSTGRES_URL = os.getenv("AGENCYFORGE_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="requires the disposable PostgreSQL CI service",
)


def test_postgresql_migration_crud_constraints_and_rollback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("ALLOW_NON_TMP_MIGRATIONS", "1")
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)

    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        assert inspector.has_table("users")
        assert inspector.has_table("leads")
        assert "ix_ai_sessions_owner_user_id" in {
            index["name"] for index in inspector.get_indexes("ai_sessions")
        }
        package_features = next(
            column["type"]
            for column in inspector.get_columns("packages")
            if column["name"] == "features"
        )
        assert isinstance(package_features, JSONB)

        with Session(engine) as session:
            admin = User(
                full_name="Postgres Admin",
                email=f"pg-{uuid.uuid4().hex}@example.test",
                hashed_password="test-scrypt-hash",
                role="admin",
                is_active=True,
            )
            package = Package(
                name=f"Postgres package {uuid.uuid4().hex[:8]}",
                slug=f"postgres-{uuid.uuid4().hex}",
                description="Disposable integration package",
                min_price=Decimal("250.00"),
                max_price=Decimal("500.00"),
                currency="BDT",
                features=["responsive", "JSONB read"],
                is_active=True,
                display_order=1,
            )
            session.add_all([admin, package])
            session.flush()

            lead = Lead(
                contact_name="Integration User",
                business_name="Postgres Test Shop",
                email=f"lead-{uuid.uuid4().hex}@example.test",
                business_type="Retail",
                project_description="Test JSONB and package foreign key",
                required_pages=["Home", "Shop"],
                required_features=["Catalog"],
                package_id=package.id,
                status="new",
            )
            ai_session = AISession(
                id=uuid.uuid4(),
                owner_user_id=admin.id,
                conversation_history=[{"role": "user", "content": {"goal": "shop"}}],
                status="active",
            )
            session.add_all([lead, ai_session])
            session.commit()

            loaded_lead = session.scalar(select(Lead).where(Lead.id == lead.id))
            loaded_ai = session.get(AISession, ai_session.id)
            assert loaded_lead.required_pages == ["Home", "Shop"]
            assert loaded_lead.package_id == package.id
            assert loaded_ai.owner_user_id == admin.id
            assert loaded_ai.conversation_history[0]["content"]["goal"] == "shop"
            assert loaded_ai.id == ai_session.id

            rolled_back_email = f"rollback-{uuid.uuid4().hex}@example.test"
            with pytest.raises(RuntimeError, match="rollback sentinel"):
                with session.begin_nested():
                    session.add(
                        User(
                            full_name="Rolled Back",
                            email=rolled_back_email,
                            hashed_password="test-scrypt-hash",
                        )
                    )
                    session.flush()
                    raise RuntimeError("rollback sentinel")
            session.rollback()
            assert session.scalar(
                select(User).where(User.email == rolled_back_email)
            ) is None

            session.add(
                Lead(
                    contact_name="Invalid FK",
                    business_name="Invalid",
                    email=f"fk-{uuid.uuid4().hex}@example.test",
                    business_type="Other",
                    project_description="Must be rejected",
                    required_pages=[],
                    required_features=[],
                    package_id=2_147_483_647,
                    status="new",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_postgresql_registration_admin_authorization_and_lead_status(monkeypatch):
    """Exercise the application API against PostgreSQL, including its DB roles."""
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("JWT_SECRET_KEY", "postgres-integration-secret-key-over-32-bytes")
    get_settings.cache_clear()
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    created_emails = []
    created_lead_emails = []

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with Session(engine) as db:
            admin_email = f"api-admin-{uuid.uuid4().hex}@example.com"
            staff_email = f"api-staff-{uuid.uuid4().hex}@example.com"
            created_emails.extend([admin_email, staff_email])
            admin = User(
                full_name="API Admin",
                email=admin_email,
                hashed_password="unused-test-password-hash",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            admin_token = create_access_token(admin.id, admin.role)

        async def exercise_api():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://agencyforge.test"
            ) as client:
                registration = await client.post(
                    "/api/auth/register",
                    headers={"Origin": "http://agencyforge.test"},
                    json={
                        "full_name": "Postgres Registered Staff",
                        "email": staff_email,
                        "password": "postgres-staff-password-123",
                    },
                )
                assert registration.status_code == 201, registration.text
                assert registration.json()["user"]["role"] == "staff"

                staff_token = registration.cookies.get("access_token")
                assert staff_token
                staff_users = await client.get(
                    "/api/admin/users",
                    headers={"Authorization": f"Bearer {staff_token}"},
                )
                assert staff_users.status_code == 403

                client.cookies.delete("access_token")
                admin_headers = {"Authorization": f"Bearer {admin_token}"}
                users = await client.get("/api/admin/users", headers=admin_headers)
                assert users.status_code == 200
                assert any(item["email"] == staff_email for item in users.json()["items"])

                inquiry_email = f"pg-inquiry-{uuid.uuid4().hex}@example.com"
                created_lead_emails.append(inquiry_email)
                inquiry = await client.post(
                    "/api/leads/",
                    json={
                        "contact_name": "Postgres Inquiry",
                        "business_name": "PG Cafe",
                        "email": inquiry_email,
                        "business_type": "Restaurant / Cafe",
                        "project_description": "Postgres API lead persistence",
                        "required_pages": ["Home", "Menu"],
                        "required_features": ["Contact form"],
                    },
                )
                assert inquiry.status_code == 201, inquiry.text
                lead_id = inquiry.json()["id"]

                changed = await client.patch(
                    f"/api/leads/{lead_id}/status",
                    headers=admin_headers,
                    json={"status": "contacted"},
                )
                assert changed.status_code == 200, changed.text
                assert changed.json()["status"] == "contacted"

                inactive = await client.patch(
                    f"/api/admin/users/{registration.json()['user']['id']}/status",
                    headers=admin_headers,
                    json={"is_active": False},
                )
                assert inactive.status_code == 200, inactive.text
                assert inactive.json()["is_active"] is False

        asyncio.run(exercise_api())
    finally:
        app.dependency_overrides.pop(get_db, None)
        with Session(engine) as db:
            db.query(Lead).filter(Lead.email.in_(created_lead_emails)).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.email.in_(created_emails)).delete(
                synchronize_session=False
            )
            db.commit()
        engine.dispose()
        get_settings.cache_clear()
