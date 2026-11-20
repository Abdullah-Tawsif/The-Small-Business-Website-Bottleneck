import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import services.ai_scoping_service as ai_service
from database.database import Base
from models.ai_session import AISession
from models.lead import Lead  # Register the referenced table on shared metadata.
from models.user import User
from schemas.scoping import ScopingRequest


def make_payload(**overrides):
    values = {
        "message": "We need a website for an online shop",
        "business_name": "Test Shop",
        "business_type": "Retail",
        "goals": ["sell products online"],
    }
    values.update(overrides)
    return ScopingRequest(**values)


def test_ai_scoping_persists_deterministic_fallback(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ai-scoping.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        ai_service,
        "generate_external_ai_scope",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    try:
        with Session(engine, expire_on_commit=False) as db:
            response = ai_service.generate_scope(db, make_payload())
            session = db.get(AISession, response.session_id)

            assert session is not None
            assert response.session_token
            assert session.owner_user_id is None
            assert session.guest_capability_hash != response.session_token
            assert session.expires_at is not None
            assert session.status == "active"
            assert session.fallback_used is True
            assert session.provider == "deterministic"
            assert session.total_tokens == 0
            assert len(session.conversation_history) == 2
            assert session.conversation_history[0]["role"] == "user"
            assert session.conversation_history[1]["role"] == "assistant"
            assert response.required_pages
            assert response.required_features
    finally:
        engine.dispose()


def test_ai_scoping_continues_existing_session_without_external_provider(
    monkeypatch,
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'ai-continuation.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        ai_service,
        "generate_external_ai_scope",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    try:
        with Session(engine, expire_on_commit=False) as db:
            first = ai_service.generate_scope(db, make_payload())
            followup = make_payload(
                session_id=first.session_id,
                session_token=first.session_token,
                message="Please include a contact page too",
                required_pages=["Contact"],
            )

            second = ai_service.generate_scope(db, followup)
            session = db.get(AISession, first.session_id)

            assert second.session_id == first.session_id
            assert second.session_token is None
            assert session is not None
            assert len(session.conversation_history) == 4
            assert session.conversation_history[2]["role"] == "user"
            assert session.conversation_history[2]["content"]["message"] == (
                "Please include a contact page too"
            )
    finally:
        engine.dispose()


def test_authenticated_ai_session_owner_can_continue_but_other_user_cannot(
    monkeypatch, tmp_path
):
    engine = create_engine(f"sqlite:///{tmp_path / 'owned-sessions.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        ai_service,
        "generate_external_ai_scope",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    try:
        with Session(engine, expire_on_commit=False) as db:
            db.add_all([
                User(full_name="Owner", email="owner@example.com", hashed_password="x"),
                User(full_name="Other", email="other@example.com", hashed_password="x"),
            ])
            db.commit()
            created = ai_service.generate_scope(db, make_payload(), owner_user_id=1)
            session = db.get(AISession, created.session_id)
            assert session.owner_user_id == 1
            assert created.session_token is None
            continued = ai_service.generate_scope(
                db,
                make_payload(session_id=created.session_id),
                owner_user_id=1,
            )
            assert continued.session_id == created.session_id
            with pytest.raises(ValueError, match="unavailable"):
                ai_service.generate_scope(
                    db,
                    make_payload(session_id=created.session_id),
                    owner_user_id=2,
                )
    finally:
        engine.dispose()


def test_guest_session_requires_capability_and_rejects_expired_session(
    monkeypatch, tmp_path
):
    from datetime import UTC, datetime, timedelta

    engine = create_engine(f"sqlite:///{tmp_path / 'guest-sessions.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        ai_service,
        "generate_external_ai_scope",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    try:
        with Session(engine, expire_on_commit=False) as db:
            created = ai_service.generate_scope(db, make_payload())
            with pytest.raises(ValueError, match="unavailable"):
                ai_service.generate_scope(
                    db,
                    make_payload(session_id=created.session_id),
                )
            with pytest.raises(ValueError, match="unavailable"):
                ai_service.generate_scope(
                    db,
                    make_payload(
                        session_id=created.session_id,
                        session_token="x" * 40,
                    ),
                    guest_capability="x" * 40,
                )
            followed = ai_service.generate_scope(
                db,
                make_payload(
                    session_id=created.session_id,
                    session_token=created.session_token,
                ),
                guest_capability=created.session_token,
            )
            session = db.get(AISession, created.session_id)
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
            with pytest.raises(ValueError, match="unavailable"):
                ai_service.generate_scope(
                    db,
                    make_payload(
                        session_id=followed.session_id,
                        session_token=created.session_token,
                    ),
                    guest_capability=created.session_token,
                )
    finally:
        engine.dispose()


def test_ai_account_budget_cannot_be_bypassed_with_new_session_keys():
    from config.settings import Settings
    from routes.scoping import _LOCAL_AI_BUDGETS, _reserve_local

    _LOCAL_AI_BUDGETS.clear()
    settings = Settings(
        _env_file=None,
        ai_account_daily_limit=1,
        ai_session_daily_limit=10,
        ai_global_daily_limit=10,
    )
    assert _reserve_local("same-account", "session-one", settings)[0] is True
    assert _reserve_local("same-account", "fresh-session-id", settings)[0] is False
    _LOCAL_AI_BUDGETS.clear()


def test_production_ai_budget_fails_closed_during_redis_outage(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException
    from redis.exceptions import ConnectionError as RedisConnectionError
    from starlette.requests import Request

    from config.settings import Settings
    from routes.scoping import _reserve_ai_budget

    class OfflineRedis:
        async def eval(self, *_args):
            raise RedisConnectionError("unavailable")

    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=OfflineRedis()))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/scoping/",
            "headers": [],
            "client": ("192.0.2.20", 1234),
            "app": app,
        }
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql://agency:secret@localhost/agencyforge",
            rate_limit_redis_url="redis://redis.example/0",
            jwt_secret_key="test-only-random-signing-key-material-0123456789",
        ),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(_reserve_ai_budget(request, None, None))
    assert error.value.status_code == 503


def test_guest_budgets_follow_trusted_proxy_identity(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException
    from starlette.requests import Request

    from config.settings import Settings
    from routes.scoping import _LOCAL_AI_BUDGETS, _reserve_ai_budget

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: Settings(
            _env_file=None,
            trusted_proxy_cidrs="10.10.0.0/16",
            ai_account_daily_limit=1,
            ai_session_daily_limit=5,
            ai_global_daily_limit=10,
        ),
    )
    _LOCAL_AI_BUDGETS.clear()

    def request_for(client_ip):
        return Request({
            "type": "http",
            "method": "POST",
            "path": "/api/scoping/",
            "headers": [(b"x-forwarded-for", client_ip.encode("ascii"))],
            "client": ("10.10.0.8", 12345),
            "app": SimpleNamespace(state=SimpleNamespace()),
        })

    async def reserve(request):
        try:
            await _reserve_ai_budget(request, None, None)
            return True
        except HTTPException as error:
            if error.status_code != 429:
                raise
            return False

    try:
        assert asyncio.run(reserve(request_for("198.51.100.10"))) is True
        # Same guest through another request shares the same identity/budget.
        assert asyncio.run(reserve(request_for("198.51.100.10"))) is False
        # A separate guest behind the same proxy receives its own account cap.
        assert asyncio.run(reserve(request_for("198.51.100.11"))) is True
    finally:
        _LOCAL_AI_BUDGETS.clear()
