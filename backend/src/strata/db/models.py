"""Core ORM models.

Tables
------
``core_users``
    Platform-level user identity.  FK target for all plugins.
``core_storage_instances``
    Admin-created storage instances (one per template configuration).
``core_storage_user_configs``
    Per-user config overrides and enable/disable state for each instance.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from strata.db.base import Base
from strata.utils import create_uuid, utcnow


class CoreUser(Base):
    """Platform-level user identity record."""

    __tablename__ = "core_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    storage_user_configs: Mapped[list["CoreStorageUserConfig"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CoreUser id={self.id!r} created={self.created_at}>"


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

    user_configs: Mapped[list["CoreStorageUserConfig"]] = relationship(
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
        instance_id: FK → ``core_storage_instances.id`` CASCADE.
        user_id: FK → ``core_users.id`` CASCADE.
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
