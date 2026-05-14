"""Alembic migration environment for strata-storage-smb."""

from strata_storage_smb.models import Base

from strata.db.utils import MigrationEnv

MigrationEnv(target_metadata=Base.metadata, plugin_id="storage_smb").run()
