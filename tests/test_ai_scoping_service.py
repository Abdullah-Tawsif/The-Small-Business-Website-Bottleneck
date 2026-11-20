from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import services.ai_scoping_service as ai_service
from database.database import Base
from models.ai_session import AISession
from models.lead import Lead  # Register the referenced table on shared metadata.
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
                message="Please include a contact page too",
                required_pages=["Contact"],
            )

            second = ai_service.generate_scope(db, followup)
            session = db.get(AISession, first.session_id)

            assert second.session_id == first.session_id
            assert session is not None
            assert len(session.conversation_history) == 4
            assert session.conversation_history[2]["role"] == "user"
            assert session.conversation_history[2]["content"]["message"] == (
                "Please include a contact page too"
            )
    finally:
        engine.dispose()
