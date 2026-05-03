"""Core user identity table.

This module defines the single platform-level user record: ``strata_users``.
It contains only the identity — a UUID and a creation timestamp.
Auth-specific data (password hashes, tokens) lives in the ``jwt_auth``
plugin.  Per-user storage credentials live in their respective plugins.

Why here and not in a plugin
-----------------------------
Any plugin that stores per-user data needs a stable foreign key target that
does not depend on which auth backend is installed.  If the FK pointed at
``jwt_auth_users``, every storage plugin would gain an implicit dependency on
the JWT auth plugin.  By placing the identity table in the core we have:

- A single, stable FK target for all plugins: ``strata_users.id``.
- Clean cascade deletes: deleting a user row removes all plugin-owned rows
  (credentials, tokens, preferences) automatically.
- Auth plugins are free to come and go without breaking storage plugins.

Migration ordering
------------------
The :class:`CoreUsersDbContributor` is registered into the
:class:`~strata.plugins.registry.DbRegistry` by :func:`strata.main.lifespan`
*before* ``plugin_loader.load_and_register()`` is called.  Alembic therefore
runs the ``strata_core`` migration before any plugin migration, guaranteeing
that ``strata_users`` exists when plugins that FK to it are migrated.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from strata.db import plugin_base

# The core Base is produced via plugin_base() like any other contributor so
# that its MetaData object is self-contained and registerable independently.
Base = plugin_base("strata_core")


def _uuid() -> str:
    return str(uuid.uuid4())


class StrataUser(Base):
    """Platform-level user identity record.

    This row is the FK target for every plugin that stores per-user data.
    It carries no auth-specific fields; those belong to the auth plugin that
    created this record.

    Attributes:
        id: UUID primary key (VARCHAR(36)), stable across auth backend changes.
        created_at: UTC timestamp set by the database server on insert.
    """

    __tablename__ = "strata_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<StrataUser id={self.id!r} created={self.created_at}>"
