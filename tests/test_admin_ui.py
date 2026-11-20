from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import database.database as database_module
from config.settings import get_settings
from database.database import Base, get_db
from main import app
from models.user import User
from utils.security import create_access_token, hash_password


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    """Run admin page/API requests against a disposable SQLite database."""
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'admin-ui-tests.sqlite'}",
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
        "isolated-admin-ui-tests-secret-at-least-32-bytes",
    )
    get_settings.cache_clear()

    def override_get_db():
        with test_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            with test_sessions() as db:
                admin = User(
                    full_name="Test Administrator",
                    email="admin-test@example.invalid",
                    hashed_password=hash_password("test-admin-password-123"),
                    role="admin",
                    is_active=True,
                )
                staff = User(
                    full_name="Test Staff",
                    email="staff-test@example.invalid",
                    hashed_password=hash_password("test-staff-password-123"),
                    role="staff",
                    is_active=True,
                )
                db.add_all([admin, staff])
                db.commit()
                db.refresh(admin)
                db.refresh(staff)

            client.cookies.set(
                get_settings().access_token_cookie_name,
                create_access_token(admin.id, admin.role),
            )
            client.cookies.set("csrf_token", "admin-ui-csrf-token")
            yield client, staff.id
    finally:
        app.dependency_overrides.pop(get_db, None)
        get_settings.cache_clear()
        test_engine.dispose()


def test_admin_page_and_user_api_require_admin(admin_client):
    client, staff_id = admin_client
    admin_cookie_name = get_settings().access_token_cookie_name
    admin_token = client.cookies.get(admin_cookie_name)

    client.cookies.delete(admin_cookie_name)
    page_redirect = client.get("/admin", follow_redirects=False)
    assert page_redirect.status_code == 303
    assert page_redirect.headers["location"] == "/login"
    assert client.get("/api/admin/users").status_code == 401

    staff_token = create_access_token(staff_id, "staff")
    client.cookies.set(admin_cookie_name, staff_token)
    page_redirect = client.get("/admin", follow_redirects=False)
    assert page_redirect.status_code == 303
    assert page_redirect.headers["location"] == "/dashboard"
    assert client.get("/api/admin/users").status_code == 403

    client.cookies.set(admin_cookie_name, admin_token)
    page = client.get("/admin")
    assert page.status_code == 200
    assert "Admin " in page.text and "overview." in page.text


def test_admin_user_api_returns_paginated_contract_and_updates_status(admin_client):
    client, staff_id = admin_client

    response = client.get("/api/admin/users?page=1&page_size=1")
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 2
    assert result["page"] == 1
    assert result["page_size"] == 1
    assert result["total_pages"] == 2
    assert len(result["items"]) == 1
    assert set(result["items"][0]) == {
        "id",
        "full_name",
        "email",
        "role",
        "is_active",
        "created_at",
    }

    update = client.patch(
        f"/api/admin/users/{staff_id}/status",
        json={"is_active": False},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": "admin-ui-csrf-token",
        },
    )
    assert update.status_code == 200
    assert update.json()["is_active"] is False


def test_admin_page_uses_existing_lead_contract(admin_client):
    client, _ = admin_client
    origin = {"Origin": "http://testserver"}
    response = client.get("/api/leads/?limit=20")
    assert response.status_code == 200
    assert response.json() == []

    created = client.post(
        "/api/leads/",
        headers=origin,
        json={
            "contact_name": "CSRF Customer",
            "business_name": "CSRF Business",
            "email": "csrf-lead@example.com",
            "business_type": "Retail",
            "project_description": "A sufficiently detailed project description.",
        },
    )
    assert created.status_code == 201
    lead_id = created.json()["id"]

    missing_token = client.patch(
        f"/api/leads/{lead_id}/status",
        headers=origin,
        json={"status": "contacted"},
    )
    assert missing_token.status_code == 403
    invalid_token = client.patch(
        f"/api/leads/{lead_id}/status",
        headers={**origin, "X-CSRF-Token": "invalid-csrf-token"},
        json={"status": "contacted"},
    )
    assert invalid_token.status_code == 403
    valid_token = client.patch(
        f"/api/leads/{lead_id}/status",
        headers={**origin, "X-CSRF-Token": "admin-ui-csrf-token"},
        json={"status": "contacted"},
    )
    assert valid_token.status_code == 200
    assert valid_token.json()["status"] == "contacted"

    assert client.get("/api/leads/0").status_code == 422
    assert client.patch(
        "/api/leads/0/status",
        json={"status": "contacted"},
        headers={
            **origin,
            "X-CSRF-Token": "admin-ui-csrf-token",
        },
    ).status_code == 422

    template = Path("templates/admin/admin.html").read_text()
    assert 'fetch("/api/leads/?limit=20"' in template
    assert "lead.package_id" in template
    assert "lead.status" in template
    assert 'fetch("/api/admin/leads"' not in template


def test_dashboard_describes_only_existing_account_actions(admin_client):
    client, staff_id = admin_client
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Start a project inquiry" in response.text
    assert "Back to home" in response.text
    assert "starter dashboard" not in response.text
    assert "Authentication successful" not in response.text
    assert 'href="/admin"' in response.text

    client.cookies.set(
        get_settings().access_token_cookie_name,
        create_access_token(staff_id, "staff"),
    )
    staff_dashboard = client.get("/dashboard")
    assert staff_dashboard.status_code == 200
    assert 'href="/admin"' not in staff_dashboard.text


def test_readme_documents_the_administrator_page():
    readme = Path("README.md").read_text()
    assert "| GET | `/admin` | Administrator-only overview |" in readme


def test_home_preview_continue_opens_the_real_inquiry_workflow():
    home_page = Path("templates/home/index.html").read_text()
    home_styles = Path("static/css/home/index.css").read_text()
    assert 'href="/static/css/home/index.css"' in home_page
    assert '<a class="button" href="/inquiry">Start scoping' in home_page
    assert '<a href="/inquiry" aria-label="Continue to project inquiry">Continue</a>' in home_page
    assert '<button type="button">Continue</button>' not in home_page
    assert ".preview-bottom a" in home_styles


def test_unauthenticated_dashboard_redirects_to_sign_in(admin_client):
    client, _ = admin_client
    client.cookies.clear()

    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_inquiry_budget_fields_have_accessible_names():
    inquiry_page = Path("templates/inquiry/index.html").read_text()
    assert 'id="budget-min"' in inquiry_page
    assert 'aria-label="Minimum budget (BDT)"' in inquiry_page
    assert 'id="budget-max"' in inquiry_page
    assert 'aria-label="Maximum budget (BDT)"' in inquiry_page


def test_sign_in_page_does_not_offer_unsupported_controls():
    login_page = Path("templates/auth/login.html").read_text()
    assert "name=\"remember\"" not in login_page
    assert 'href="#" class="muted-link">Forgot password?' not in login_page
    assert "Password recovery is not available yet." in login_page


def test_admin_page_does_not_display_undefined_open_session_metric():
    admin_page = Path("templates/admin/admin.html").read_text()
    assert "Open sessions" not in admin_page
    assert "stat-sessions" not in admin_page


def test_readme_test_example_uses_an_existing_test_module():
    readme = Path("README.md").read_text()
    assert "python -m pytest tests/test_security.py -v" in readme
    assert "python -m pytest tests/test_auth.py -v" not in readme


def test_architecture_documents_current_admin_registration_and_page():
    architecture = Path("ARCHITECTURE.md").read_text()
    assert "included by `main.py`" in architecture
    assert "must be registered by the Team Lead" not in architecture
    assert "`/admin` (active administrators only)" in architecture


def test_registration_form_matches_backend_password_minimum():
    registration_page = Path("templates/auth/register.html").read_text()
    assert 'name="password"' in registration_page
    assert 'minlength="10"' in registration_page
    assert "Use at least 10 characters." in registration_page
    assert "Use at least 8 characters." not in registration_page


def test_admin_page_uses_existing_account_status_api_and_pagination():
    admin_page = Path("templates/admin/admin.html").read_text()
    assert 'id="users-previous"' in admin_page
    assert 'id="users-next"' in admin_page
    assert 'fetch(`/api/admin/users/${userId}/status`' in admin_page
    assert 'JSON.stringify({is_active: !isActive})' in admin_page
    assert '"X-CSRF-Token": csrfToken()' in admin_page
    assert "Number(user.id) === currentAdminId" in admin_page


def test_admin_template_renders_current_admin_identifier():
    templates = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html"]),
    )

    rendered = templates.get_template("admin/admin.html").render(
        user=SimpleNamespace(id=42)
    )

    assert "const currentAdminId = 42;" in rendered
    assert "{{ user.id }}" not in rendered


def test_admin_table_values_include_mobile_labels():
    admin_page = Path("templates/admin/admin.html").read_text()
    assert 'data-label="Name"' in admin_page
    assert 'data-label="Email"' in admin_page
    assert 'data-label="Account"' in admin_page
    assert 'data-label="Contact"' in admin_page


def test_dashboard_and_admin_sign_out_show_failure_feedback():
    dashboard = Path("templates/dashboard/index.html").read_text()
    admin_page = Path("templates/admin/admin.html").read_text()

    assert 'id="logout-message"' in dashboard
    assert "Unable to sign out. Please try again." in dashboard
    assert "'X-CSRF-Token':csrfToken()" in dashboard
    assert 'type="button" id="logout-button"' in admin_page
    assert "Unable to sign out. Please try again." in admin_page
    assert '"X-CSRF-Token": csrfToken()' in admin_page


def test_admin_async_tables_announce_loading_and_result_changes():
    admin_page = Path("templates/admin/admin.html").read_text()
    assert 'id="users-body" class="table-body" aria-live="polite" aria-busy="true"' in admin_page
    assert 'id="leads-body" class="table-body" aria-live="polite" aria-busy="true"' in admin_page
    assert 'body.setAttribute("aria-busy", "false")' in admin_page


def test_admin_navigation_has_responsive_keyboard_controls():
    admin_page = Path("templates/admin/admin.html").read_text()

    assert 'id="admin-menu-toggle"' in admin_page
    assert 'aria-controls="admin-nav-links"' in admin_page
    assert 'adminNavigation.classList.toggle("is-open", isOpen)' in admin_page
    assert 'event.key !== "Escape"' in admin_page
