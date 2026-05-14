"""Initial smb_storage schema: per-user SMB credentials.

Revision ID: 0001
Revises:
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("smb_storage",)
depends_on: str | Sequence[str] | None = None
# Ordering guarantee: core_users is created by the core migration which
# always runs before plugin migrations (see DbRegistry insertion order in
# strata.main.lifespan).


def upgrade() -> None:
    op.create_table(
        "smb_storage_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            # FK to the platform identity — no dependency on auth_jwt.
            sa.ForeignKey("core_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("share", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False, server_default=""),
        sa.Column("smb_username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_smb_storage_credentials_user_id",
        "smb_storage_credentials",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("smb_storage_credentials")
