"""Alembic migration environment for the Strata core schema."""

from strata.db.base import Base
from strata.db.utils import MigrationEnv, version_table_name

env = MigrationEnv(
    target_metadata=Base.metadata,
    version_table=version_table_name("strata_core"),
)
env.run()
