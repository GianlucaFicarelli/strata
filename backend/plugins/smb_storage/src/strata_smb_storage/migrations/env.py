"""Alembic migration environment for strata-smb-storage."""

from strata_smb_storage.models import Base

from strata.db.utils import MigrationEnv

MigrationEnv(target_metadata=Base.metadata, plugin_id="smb_storage").run()
