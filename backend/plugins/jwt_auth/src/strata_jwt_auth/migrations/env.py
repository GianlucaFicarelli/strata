"""Alembic migration environment for strata-jwt-auth."""

from strata_jwt_auth.models import Base

from strata.db.utils import MigrationEnv, version_table_name

env = MigrationEnv(
    target_metadata=Base.metadata,
    version_table=version_table_name("jwt_auth"),
)
env.run()
