"""Initial jwt_auth schema: users and refresh_tokens tables.

Revision ID: 0001
Revises:
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("jwt_auth",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jwt_auth_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_jwt_auth_users_id", "jwt_auth_users", ["id"])
    op.create_index("ix_jwt_auth_users_username", "jwt_auth_users", ["username"], unique=True)

    op.create_table(
        "jwt_auth_refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("jwt_auth_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_jwt_auth_refresh_tokens_user_id",
        "jwt_auth_refresh_tokens",
        ["user_id"],
    )
    op.create_index(
        "uq_jwt_auth_refresh_tokens_token_hash",
        "jwt_auth_refresh_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("jwt_auth_refresh_tokens")
    op.drop_table("jwt_auth_users")
