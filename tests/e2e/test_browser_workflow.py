"""Playwright smoke coverage for real desktop and mobile user journeys."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from models.package import Package
from models.user import User
from utils.security import hash_password


ROOT = Path(__file__).resolve().parents[2]
RESPONSIVE_WIDTHS = (375, 430, 768, 1366, 1920)
pytestmark = pytest.mark.skipif(
    os.getenv("AGENCYFORGE_RUN_BROWSER_TESTS") != "1",
    reason="Playwright browser suite runs in the dedicated CI browser job.",
)


def assert_no_horizontal_overflow(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    dimensions = page.evaluate(
        """() => ({
            document: document.documentElement.scrollWidth,
            viewport: window.innerWidth
        })"""
    )
    assert dimensions["document"] <= dimensions["viewport"], dimensions


def capture_responsive_screenshots(page, directory, page_name):
    for width in RESPONSIVE_WIDTHS:
        page.set_viewport_size({"width": width, "height": 900})
        page.screenshot(
            path=str(directory / f"{page_name}-{width}.png"),
            full_page=True,
        )
    page.set_viewport_size({"width": 1366, "height": 900})


@pytest.fixture
def running_app(tmp_path):
    database_path = tmp_path / "agencyforge-browser.sqlite"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "ALLOW_NON_TMP_MIGRATIONS": "1",
            "ENVIRONMENT": "development",
            "JWT_SECRET_KEY": "browser-suite-test-signing-key-at-least-32-bytes",
            "RATE_LIMIT_REDIS_URL": "",
            "OPENAI_API_KEY": "",
        }
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    engine = create_engine(database_url)
    admin_email = "browser-admin@example.com"
    admin_password = "browser-admin-password-123"
    with Session(engine) as db:
        db.add_all(
            [
                User(
                    full_name="Browser Administrator",
                    email=admin_email,
                    hashed_password=hash_password(admin_password),
                    role="admin",
                    is_active=True,
                ),
                Package(
                    name="Browser Starter",
                    slug="browser-starter",
                    description="A package seeded for browser verification.",
                    min_price=Decimal("25000"),
                    max_price=Decimal("45000"),
                    currency="BDT",
                    features=["Responsive design", "Contact form"],
                    is_active=True,
                    display_order=1,
                ),
            ]
        )
        db.commit()
    engine.dispose()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("AgencyForge browser test server exited during startup.")
            try:
                with urlopen(f"{base_url}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError("AgencyForge browser test server did not become healthy.")
        yield base_url, admin_email, admin_password, database_url, tmp_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_registration_inquiry_admin_controls_and_responsive_pages(running_app):
    base_url, admin_email, admin_password, _database_url, artifacts = running_app
    console_errors = []
    request_failures = []
    screenshots = Path(
        os.getenv("AGENCYFORGE_SCREENSHOT_DIR", str(artifacts / "screenshots"))
    )
    screenshots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on(
            "requestfailed",
            lambda request: request_failures.append((request.url, request.failure)),
        )

        home_response = page.goto(base_url)
        assert home_response and home_response.status == 200
        assert page.title().startswith("AgencyForge")
        assert page.locator("link[href='/static/css/agencyforge-theme.css']").count() == 1
        capture_responsive_screenshots(page, screenshots, "home")

        page.set_viewport_size({"width": 375, "height": 812})
        page.reload()
        page.screenshot(path=str(screenshots / "home-mobile.png"), full_page=True)
        mobile_overflow = page.evaluate(
            """() => ({
                width: document.documentElement.scrollWidth,
                viewport: window.innerWidth,
                elements: [...document.querySelectorAll('body *')]
                    .map(element => ({
                        tag: element.tagName,
                        className: typeof element.className === 'string' ? element.className : '',
                        right: Math.round(element.getBoundingClientRect().right),
                        left: Math.round(element.getBoundingClientRect().left),
                        width: Math.round(element.getBoundingClientRect().width)
                    }))
                    .filter(element => element.right > window.innerWidth + 1 || element.left < -1)
                    .slice(0, 20)
            })"""
        )
        assert mobile_overflow["width"] <= mobile_overflow["viewport"], mobile_overflow
        menu_toggle = page.get_by_role("button", name="Open navigation")
        menu_toggle.click()
        assert menu_toggle.get_attribute("aria-expanded") == "true"
        assert page.locator("#home-navigation").evaluate(
            "element => element.classList.contains('is-open')"
        )
        menu_toggle.click()
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)

        page.set_viewport_size({"width": 1366, "height": 900})
        page.goto(f"{base_url}/register")
        capture_responsive_screenshots(page, screenshots, "registration")
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)
        page.locator("input[name='name']").fill("Browser Test Staff")
        page.locator("input[name='email']").fill("browser-staff@example.com")
        page.locator("input[name='password']").fill("browser-staff-password-123")
        page.locator("input[name='confirm']").fill("browser-staff-password-123")
        page.get_by_role("button", name="Create account").click()
        page.wait_for_url("**/dashboard")
        assert page.get_by_text("Browser Test Staff").count() >= 1
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)
        capture_responsive_screenshots(page, screenshots, "dashboard")
        workspace = page.goto(f"{base_url}/user")
        assert workspace and workspace.status == 200
        assert page.get_by_text("Browser Test Staff").count() >= 1
        workspace_signout_style = page.locator("#logout-button").evaluate(
            "element => getComputedStyle(element).backgroundColor"
        )
        assert workspace_signout_style == "rgba(0, 0, 0, 0)"
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)
        capture_responsive_screenshots(page, screenshots, "user-workspace")

        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url("**/login")
        capture_responsive_screenshots(page, screenshots, "login")
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        focus_style = page.evaluate(
            """() => {
                const style = getComputedStyle(document.activeElement);
                return {outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth};
            }"""
        )
        assert focus_style == {"outlineStyle": "solid", "outlineWidth": "2px"}
        page.locator("input[name='email']").fill("browser-staff@example.com")
        page.locator("input[name='password']").fill("browser-staff-password-123")
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/dashboard")
        page.set_viewport_size({"width": 1366, "height": 900})
        page.goto(f"{base_url}/admin")
        page.wait_for_url("**/dashboard")
        assert page.get_by_text("Browser Test Staff").count() >= 1

        page.goto(f"{base_url}/inquiry")
        capture_responsive_screenshots(page, screenshots, "inquiry")
        chat_input_style = page.locator("#scoping-message").evaluate(
            "element => getComputedStyle(element).backgroundColor"
        )
        assert chat_input_style == "rgb(10, 16, 12)"
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)
        page.locator("#business-name").fill("Browser Bakery")
        page.locator("#business-type").select_option(label="Restaurant / Cafe")
        page.locator("#project-description").fill("A responsive website for bakery menus and customer inquiries.")
        page.locator("#contact-name").fill("Morgan Baker")
        page.locator("#contact-email").fill("morgan-baker@example.com")
        page.locator("#submit-inquiry").click()
        page.locator("#inquiry-status").get_by_text(
            "Your project inquiry was submitted successfully!", exact=False
        ).wait_for(timeout=15000)

        page.goto(f"{base_url}/dashboard")
        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url("**/login")
        page.locator("input[name='email']").fill(admin_email)
        page.locator("input[name='password']").fill(admin_password)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/dashboard")
        page.goto(f"{base_url}/admin")
        page.wait_for_load_state("networkidle")
        assert page.get_by_text("Morgan Baker").count() >= 1
        admin_signout_style = page.locator("#logout-button").evaluate(
            "element => getComputedStyle(element).backgroundColor"
        )
        assert admin_signout_style == "rgba(0, 0, 0, 0)"
        for width in RESPONSIVE_WIDTHS:
            assert_no_horizontal_overflow(page, width)
        capture_responsive_screenshots(page, screenshots, "admin")

        staff_row = page.locator(".table-row").filter(has_text="Browser Test Staff")
        status_button = staff_row.get_by_role(
            "button", name="Deactivate Browser Test Staff"
        )
        staff_id = status_button.get_attribute("data-user-id")
        assert staff_id
        rejected_csrf = page.evaluate(
            """async (userId) => {
                const response = await fetch(`/api/admin/users/${userId}/status`, {
                    method: 'PATCH',
                    credentials: 'same-origin',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({is_active: false})
                });
                return response.status;
            }""",
            staff_id,
        )
        assert rejected_csrf == 403

        page.set_viewport_size({"width": 375, "height": 812})
        assert_no_horizontal_overflow(page, 375)
        page.screenshot(path=str(screenshots / "admin-mobile.png"), full_page=True)
        staff_row = page.locator(".table-row").filter(has_text="Browser Test Staff")
        status_button = staff_row.get_by_role(
            "button", name="Deactivate Browser Test Staff"
        )
        status_button.click()
        page.get_by_text("Account status updated.").wait_for()
        staff_row.get_by_role("button", name="Activate Browser Test Staff").click()
        page.get_by_text("Account status updated.").wait_for()

        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        unexpected_request_failures = [
            (url, failure)
            for url, failure in request_failures
            if "ERR_ABORTED" not in (failure or "")
        ]
        assert not unexpected_request_failures, unexpected_request_failures
        expected_csrf_console_error = (
            "Failed to load resource: the server responded with a status of 403 (Forbidden)"
        )
        unexpected_console_errors = [
            error for error in console_errors if error != expected_csrf_console_error
        ]
        assert not unexpected_console_errors, unexpected_console_errors
        assert console_errors.count(expected_csrf_console_error) == 1
        page.evaluate("window.scrollTo(0, 0)")
        admin_menu_toggle = page.get_by_role("button", name="Open navigation")
        admin_menu_toggle.click()
        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url("**/login")
        protected = page.goto(f"{base_url}/dashboard")
        assert protected and protected.url.endswith("/login")
        browser.close()
