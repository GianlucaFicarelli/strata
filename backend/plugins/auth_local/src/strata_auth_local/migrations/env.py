"""Alembic environment for the auth_local plugin."""

from strata_auth_local.models import Base

from strata.db.utils import MigrationEnv

env = MigrationEnv(
    target_metadata=Base.metadata,
    plugin_id="auth_local",
)
env.run()
