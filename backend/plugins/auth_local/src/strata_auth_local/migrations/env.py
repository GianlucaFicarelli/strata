"""Alembic environment for the auth_local plugin."""

from strata.db.utils import MigrationEnv
from strata_auth_local.models import Base  # noqa: F401 — registers table with shared metadata

env = MigrationEnv(
    target_metadata=Base.metadata,
    plugin_id="auth_local",
)
env.run()
