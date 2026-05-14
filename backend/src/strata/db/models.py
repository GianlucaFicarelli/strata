"""Core user identity table.

This module defines the single platform-level user record: ``core_users``.
It contains only the identity — a UUID and a creation timestamp.
Auth-specific data (password hashes, tokens) lives in the ``auth_jwt``
plugin.  Per-user storage credentials live in their respective plugins.

Why here and not in a plugin
-----------------------------
Any plugin that stores per-user data needs a stable foreign key target that
does not depend on which auth backend is installed.  If the FK pointed at
``auth_jwt_users``, every storage plugin would gain an implicit dependency on
the JWT auth plugin.  By placing the identity table in the core we have:

- A single, stable FK target for all plugins: ``core_users.id``.
- Clean cascade deletes: deleting a user row removes all plugin-owned rows
  (credentials, tokens, preferences) automatically.
- Auth plugins are free to come and go without breaking storage plugins.

Migration ordering
------------------
The :class:`CoreUsersDbContributor` is registered into the
:class:`~strata.plugins.registry.DbRegistry` by :func:`strata.main.lifespan`
*before* ``plugin_loader.load_and_register()`` is called.  Alembic therefore
runs the ``core`` migration before any plugin migration, guaranteeing
that ``core_users`` exists when plugins that FK to it are migrated.
"""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from strata.db.base import Base
from strata.utils import create_uuid, utcnow


class CoreUser(Base):
    """Platform-level user identity record.

    This row is the FK target for every plugin that stores per-user data.
    It carries no auth-specific fields; those belong to the auth plugin that
    created this record.

    Attributes:
        id: UUID primary key (VARCHAR(36)), stable across auth backend changes.
        created_at: UTC timestamp set by the database server on insert.
    """

    __tablename__ = "core_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    def __repr__(self) -> str:
        return f"<CoreUser id={self.id!r} created={self.created_at}>"
