"""add AI session ownership and expiry

Revision ID: b38d418abc2f
Revises: a59c06e994b8
Create Date: 2026-11-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b38d418abc2f"
down_revision: Union[str, Sequence[str], None] = "a59c06e994b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # SQLite supports a REFERENCES clause on ADD COLUMN when its default
        # remains NULL. Alembic's generic constraint alteration is unsupported.
        op.execute(
            "ALTER TABLE ai_sessions ADD COLUMN owner_user_id INTEGER "
            "REFERENCES users(id)"
        )
    else:
        op.add_column(
            "ai_sessions",
            sa.Column(
                "owner_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )
    op.add_column(
        "ai_sessions",
        sa.Column("guest_capability_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ai_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_sessions_owner_user_id", "ai_sessions", ["owner_user_id"])
    op.create_index("ix_ai_sessions_expires_at", "ai_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_sessions_expires_at", table_name="ai_sessions")
    op.drop_index("ix_ai_sessions_owner_user_id", table_name="ai_sessions")
    op.drop_column("ai_sessions", "expires_at")
    op.drop_column("ai_sessions", "guest_capability_hash")
    op.drop_column("ai_sessions", "owner_user_id")
