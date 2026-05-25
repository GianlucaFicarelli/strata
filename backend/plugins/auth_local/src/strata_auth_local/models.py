"""ORM models for the auth_local plugin.

Adds one table alongside the core schema:

``auth_local_users``
    Stores the username and Argon2id password hash for each locally
    authenticated user.  The ``id`` column is a FK to ``core_users.id`` —
    the stable platform identity lives in core.
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from strata.db.base import Base


class LocalUser(Base):
    """Per-user credentials for local username/password authentication.

    Attributes:
        id: FK to ``core_users.id`` CASCADE; also the primary key.
        username: Unique login handle used on the login form.
        hashed_password: Argon2id hash produced by ``pwdlib``.
    """

    __tablename__ = "auth_local_users"

    id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<LocalUser id={self.id!r} username={self.username!r}>"
