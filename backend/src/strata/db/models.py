"""Core ORM models.

Tables
------
``core_users``
    Platform-level user identity.  FK target for all plugins.
``core_invites``
    Single-use invite tokens created by admins; consumed on registration.
``core_storage_instances``
    Admin-created storage instances (one per template configuration).
``core_storage_user_configs``
    Per-user config overrides and enable/disable state for each instance.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from strata.db.base import Base
from strata.utils import create_uuid, utcnow


class CoreUser(Base):
    """Platform-level user identity record.

    Attributes:
        id: UUID primary key.
        display_name: Required human-readable name (shown in UI).
        email: Optional unique email address.
        is_admin: Platform-wide admin flag.
        created_at: UTC creation timestamp.
        updated_at: UTC last-updated timestamp.
    """

    __tablename__ = "core_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    storage_user_configs: Mapped[list[CoreStorageUserConfig]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    invites_created: Mapped[list[CoreInvite]] = relationship(
        foreign_keys="CoreInvite.created_by",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
    invite_used: Mapped[CoreInvite | None] = relationship(
        foreign_keys="CoreInvite.used_by",
        back_populates="used_by_user",
    )

    def __repr__(self) -> str:
        return f"<CoreUser id={self.id!r} display_name={self.display_name!r}>"


class CoreInvite(Base):
    """Single-use invite token created by an admin.

    The raw token is delivered to the invitee out-of-band (e.g. email link).
    Only the SHA-256 hash is stored, so a DB leak does not expose valid tokens.

    Attributes:
        id: UUID primary key.
        token_hash: SHA-256 hex digest of the raw invite token.
        created_by: FK to core_users.id of the admin who created the invite.
        used_by: FK to core_users.id of the user who consumed the invite; NULL
            until the invite is accepted.
        expires_at: UTC expiry; the invite is invalid after this point.
        created_at: UTC creation timestamp.
    """

    __tablename__ = "core_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    used_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("core_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    creator: Mapped[CoreUser] = relationship(
        foreign_keys=[created_by], back_populates="invites_created"
    )
    used_by_user: Mapped[CoreUser | None] = relationship(
        foreign_keys=[used_by], back_populates="invite_used"
    )

    @property
    def is_used(self) -> bool:
        """Return True if the invite has already been consumed."""
        return self.used_by is not None

    def __repr__(self) -> str:
        return f"<CoreInvite id={self.id!r} used={self.is_used}>"


class CoreStorageInstance(Base):
    """Admin-created storage instance.

    One row per named configuration of a storage template.  The ``plugin_id``
    references the ``StorageTemplate.plugin_id`` registered at startup; there
    is no DB-level FK because templates live only in memory.

    The ``config_json`` column holds a JSON object with all admin-level field
    values.  Fields marked ``secret=True`` in the template's config schema are
    stored AES-256-GCM encrypted (see :mod:`strata.crypto`).

    Attributes:
        id: UUID primary key.  Used as the ``?backend=<id>`` value.
        plugin_id: Identifies which registered ``StorageTemplate`` owns this.
        instance_name: Admin-chosen display label.
        config_json: JSON-serialised admin config (secrets encrypted).
        is_enabled: Admin-level toggle; disabled instances are hidden globally.
        created_at: UTC creation timestamp.
        updated_at: UTC last-updated timestamp.
    """

    __tablename__ = "core_storage_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid)
    plugin_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instance_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    user_configs: Mapped[list[CoreStorageUserConfig]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<CoreStorageInstance id={self.id!r} plugin={self.plugin_id!r}"
            f" name={self.instance_name!r}>"
        )


class CoreStorageUserConfig(Base):
    """Per-user config state for one storage instance.

    Created when a user first interacts with an instance (enables it or saves
    user-editable fields).  The ``config_json`` column holds only the
    ``user_editable`` fields; the admin config is stored separately in
    ``CoreStorageInstance.config_json``.

    An instance is visible in the user's backend picker only when:
    - ``is_enabled`` is ``True``
    - All required ``user_editable`` fields in the template's schema are present.

    Attributes:
        id: UUID primary key.
        instance_id: FK to ``core_storage_instances.id`` CASCADE.
        user_id: FK to ``core_users.id`` CASCADE.
        is_enabled: User's personal toggle for this instance.
        config_json: JSON-serialised user-editable field values (secrets encrypted).
        updated_at: UTC last-updated timestamp.
    """

    __tablename__ = "core_storage_user_configs"
    __table_args__ = (UniqueConstraint("instance_id", "user_id", name="uq_user_instance"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid)
    instance_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("core_storage_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    instance: Mapped[CoreStorageInstance] = relationship(back_populates="user_configs")
    user: Mapped[CoreUser] = relationship(back_populates="storage_user_configs")

    def __repr__(self) -> str:
        return (
            f"<CoreStorageUserConfig instance={self.instance_id!r}"
            f" user={self.user_id!r} enabled={self.is_enabled}>"
        )
