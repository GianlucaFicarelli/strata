"""Alembic migration environment for the Strata core schema."""

from strata.db.base import Base
from strata.db.utils import MigrationEnv

MigrationEnv(target_metadata=Base.metadata, plugin_id="core").run()
