"""Create auth_local_users table.

Revision ID: 0001
Revises:
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_local_users",
        sa.Column("id", sa.String(36), sa.ForeignKey("core_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
    )
    op.create_index("ix_auth_local_users_username", "auth_local_users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_auth_local_users_username", "auth_local_users")
    op.drop_table("auth_local_users")
