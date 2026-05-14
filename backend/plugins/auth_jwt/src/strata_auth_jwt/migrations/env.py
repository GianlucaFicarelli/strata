"""Alembic migration environment for strata-jwt-auth."""

from strata_auth_jwt.models import Base

from strata.db.utils import MigrationEnv

MigrationEnv(target_metadata=Base.metadata, plugin_id="auth_jwt").run()
