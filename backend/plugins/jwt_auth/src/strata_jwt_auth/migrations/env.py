"""Alembic migration environment for strata-jwt-auth."""

from strata_jwt_auth.models import Base

from strata.db.utils import MigrationEnv

MigrationEnv(target_metadata=Base.metadata, plugin_id="jwt_auth").run()
