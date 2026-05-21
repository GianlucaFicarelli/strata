"""Add core_storage_instances and core_storage_user_configs tables.
Drop legacy storage_smb_credentials table if it exists.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "core_storage_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plugin_id", sa.String(64), nullable=False),
        sa.Column("instance_name", sa.String(255), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_core_storage_instances_plugin_id", "core_storage_instances", ["plugin_id"])

    op.create_table(
        "core_storage_user_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "instance_id",
            sa.String(36),
            sa.ForeignKey("core_storage_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("core_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("instance_id", "user_id", name="uq_user_instance"),
    )
    op.create_index(
        "ix_core_storage_user_configs_instance_id",
        "core_storage_user_configs",
        ["instance_id"],
    )
    op.create_index(
        "ix_core_storage_user_configs_user_id",
        "core_storage_user_configs",
        ["user_id"],
    )

    # Drop the superseded storage_smb_credentials table if it exists.
    # It may not exist on fresh installs (smb plugin migration may not have run yet).
    bind = op.get_bind()
    if inspect(bind).has_table("storage_smb_credentials"):
        op.drop_table("storage_smb_credentials")


def downgrade() -> None:
    op.drop_table("core_storage_user_configs")
    op.drop_table("core_storage_instances")
    # Restore storage_smb_credentials (minimal schema, no data)
    op.create_table(
        "storage_smb_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
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
