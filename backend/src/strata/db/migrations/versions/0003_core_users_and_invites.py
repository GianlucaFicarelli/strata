"""Extend core_users with display_name/email/is_admin/updated_at; add core_invites.

Drops auth_jwt tables if they exist (replaced by auth_local and core sessions).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Drop legacy auth_jwt tables (best-effort) ─────────────────────────────
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    for legacy_table in ("auth_jwt_refresh_tokens", "auth_jwt_users"):
        if legacy_table in existing_tables:
            op.drop_table(legacy_table)

    # ── Extend core_users ─────────────────────────────────────────────────────
    # SQLite does not support adding a NOT NULL column without a default in a
    # single ALTER TABLE, so we add with a server_default then remove it.
    op.add_column(
        "core_users",
        sa.Column(
            "display_name",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "core_users",
        sa.Column("email", sa.String(255), nullable=True),
    )
    op.add_column(
        "core_users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "core_users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create unique index on email (sparse — NULLs are not indexed as equal in
    # SQLite, so unique constraint + nullable works correctly).
    op.create_index("ix_core_users_email", "core_users", ["email"], unique=True)

    # ── Add core_invites ──────────────────────────────────────────────────────
    op.create_table(
        "core_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("core_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "used_by",
            sa.String(36),
            sa.ForeignKey("core_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_core_invites_token_hash", "core_invites", ["token_hash"], unique=True)
    op.create_index("ix_core_invites_created_by", "core_invites", ["created_by"])
    op.create_index("ix_core_invites_used_by", "core_invites", ["used_by"])


def downgrade() -> None:
    op.drop_table("core_invites")
    op.drop_index("ix_core_users_email", "core_users")
    op.drop_column("core_users", "updated_at")
    op.drop_column("core_users", "is_admin")
    op.drop_column("core_users", "email")
    op.drop_column("core_users", "display_name")
