"""SQLAlchemy ORM models for the JWT auth plugin.

Tables
------
``jwt_auth_users``
    Auth-specific extension of the platform identity.  The ``id`` column is
    both PK and FK to ``strata_users.id`` (one-to-one, CASCADE delete).
    Deleting the core user row removes the JWT auth row automatically.

``jwt_auth_refresh_tokens``
    Server-side refresh token store.  FKs to ``jwt_auth_users.id``.

Why FK to ``strata_users`` and not a standalone PK
----------------------------------------------------
Storage plugins (SMB, S3, …) need to store per-user credentials and must
FK to a user table that does not depend on any specific auth backend.
``strata_users`` is that stable target.  ``jwt_auth_users`` is a pure
extension of it — same UUID, extra auth columns.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from strata.db.base import Base
from strata.utils import create_uuid, utcnow


class User(Base):
    """JWT auth extension of the platform user identity.

    Shares its primary key with ``strata_users`` (one-to-one).  Deleting
    the ``strata_users`` row cascades here automatically.

    Attributes:
        id: UUID, PK and FK → ``strata_users.id`` ON DELETE CASCADE.
        username: Unique login name; case-sensitive.
        hashed_password: Argon2id hash of the plain-text password.
        is_admin: Full administrative access flag.
        created_at: UTC timestamp of account creation.
        refresh_tokens: All active refresh tokens for this user.
    """

    __tablename__ = "jwt_auth_users"

    id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strata_users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} username={self.username!r} admin={self.is_admin}>"


class RefreshToken(Base):
    """Server-side refresh token record.

    Attributes:
        id: UUID primary key.
        user_id: FK → ``jwt_auth_users.id`` ON DELETE CASCADE.
        token_hash: SHA-256 hex digest of the raw opaque token.
        expires_at: UTC expiry timestamp.
        created_at: UTC issuance timestamp.
        user: Back-reference to the owning :class:`User`.
    """

    __tablename__ = "jwt_auth_refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jwt_auth_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    def is_expired(self) -> bool:
        """Return ``True`` if this token has passed its expiry timestamp."""
        return utcnow() >= self.expires_at

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id!r} user_id={self.user_id!r} expires={self.expires_at}>"
