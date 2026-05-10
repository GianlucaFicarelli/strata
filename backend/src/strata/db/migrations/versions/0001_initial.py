"""Initial core schema: core_users identity table.

Revision ID: 0001
Revises:
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("core",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "core_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index("ix_core_users_id", "core_users", ["id"])


def downgrade() -> None:
    op.drop_table("core_users")
