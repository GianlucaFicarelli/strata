"""SQLAlchemy ORM models for the JWT auth plugin.

All tables are prefixed with ``jwt_auth_`` to avoid collisions with other
plugins in the shared Strata database.

Tables
------
``jwt_auth_users``
    One row per registered user.  Passwords are stored as Argon2 hashes via
    passlib.  The ``id`` column is a UUID stored as a string so it is
    portable across SQLite and PostgreSQL without extra extension setup.

``jwt_auth_refresh_tokens``
    Server-side store for refresh tokens.  Each row tracks one issued token;
    rows are deleted on logout or expiry.  Keeping refresh tokens in the DB
    allows true revocation without waiting for expiry.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from strata.db import plugin_base

Base = plugin_base("strata_jwt_auth")


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """Registered user account.

    Attributes:
        id: UUID primary key (stored as VARCHAR).
        username: Unique login name; case-sensitive.
        hashed_password: Argon2id hash of the plain-text password.
        is_admin: If ``True`` the user has full administrative access.
        created_at: UTC timestamp of account creation, set by the DB server.
        refresh_tokens: Back-reference to all active refresh tokens.
    """

    __tablename__ = "jwt_auth_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} username={self.username!r} admin={self.is_admin}>"


class RefreshToken(Base):
    """Server-side refresh token record.

    Storing refresh tokens in the DB allows immediate revocation (logout,
    password change) without waiting for the short-lived access token to
    expire on its own.

    Attributes:
        id: UUID primary key.
        user_id: FK to :class:`User`.
        token_hash: SHA-256 hex digest of the raw token.  The raw token is
            sent to the client; only the hash is stored server-side.
        expires_at: UTC expiry; rows past this timestamp are treated as
            invalid and can be pruned by a background job.
        created_at: UTC timestamp of issuance.
        user: Back-reference to the owning :class:`User`.
    """

    __tablename__ = "jwt_auth_refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jwt_auth_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    def is_expired(self) -> bool:
        """Return ``True`` if this token has passed its expiry timestamp."""
        return _utcnow() >= self.expires_at

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id!r} user_id={self.user_id!r} expires={self.expires_at}>"
