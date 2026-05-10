"""Alembic migration environment for strata-smb-storage."""

from strata_smb_storage.models import Base

from strata.db.utils import MigrationEnv, version_table_name

env = MigrationEnv(
    target_metadata=Base.metadata,
    version_table=version_table_name("smb_storage"),
)
env.run()
