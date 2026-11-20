
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


# SQLite uses JSON; PostgreSQL uses native JSONB.
AI_SESSION_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class AISession(Base):
    """
    Stores AI conversation history and usage statistics
    for website project scoping sessions.
    """

    __tablename__ = "ai_sessions"

    # --------------------------------------------------
    # 1. DATABASE CONSTRAINTS AND INDEXES
    # --------------------------------------------------

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'failed')",
            name="ck_ai_sessions_status",
        ),
        CheckConstraint(
            "prompt_tokens >= 0",
            name="ck_ai_sessions_prompt_tokens",
        ),
        CheckConstraint(
            "completion_tokens >= 0",
            name="ck_ai_sessions_completion_tokens",
        ),
        CheckConstraint(
            "total_tokens >= 0",
            name="ck_ai_sessions_total_tokens",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_ai_sessions_duration",
        ),
        Index(
            "ix_ai_sessions_lead_id",
            "lead_id",
        ),
        Index(
            "ix_ai_sessions_status_created",
            "status",
            "created_at",
        ),
        Index("ix_ai_sessions_owner_user_id", "owner_user_id"),
    )

    # --------------------------------------------------
    # 2. PRIMARY KEY
    # --------------------------------------------------

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --------------------------------------------------
    # 3. ASSOCIATED CUSTOMER LEAD
    # --------------------------------------------------

    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )

    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    guest_capability_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # --------------------------------------------------
    # 4. AI PROVIDER INFORMATION
    # --------------------------------------------------

    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    # --------------------------------------------------
    # 5. CONVERSATION HISTORY
    # --------------------------------------------------

    conversation_history: Mapped[list[dict[str, Any]]] = (
        mapped_column(
            AI_SESSION_JSON_TYPE,
            default=list,
            nullable=False,
        )
    )

    # --------------------------------------------------
    # 6. TOKEN USAGE
    # --------------------------------------------------

    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # --------------------------------------------------
    # 7. PERFORMANCE TRACKING
    # --------------------------------------------------

    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    fallback_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # --------------------------------------------------
    # 8. SESSION STATUS
    # --------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # --------------------------------------------------
    # 9. TIMESTAMPS
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 10. OBJECT REPRESENTATION
    # --------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<AISession("
            f"id={self.id}, "
            f"status='{self.status}', "
            f"total_tokens={self.total_tokens}"
            f")>"
        )
