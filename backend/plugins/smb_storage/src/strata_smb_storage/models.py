"""SQLAlchemy ORM models for the SMB storage plugin.

Table
-----
``smb_storage_credentials``
    Per-user SMB connection parameters.  Each row stores the host, share,
    domain, username, and an encrypted password for one user on one share.

    ``user_id`` is a FK to ``core_users.id`` with CASCADE delete — no
    dependency on ``jwt_auth`` or any other auth plugin.

Encryption
----------
Passwords are stored encrypted.  The encryption helpers live in
``strata_smb_storage.crypto`` (not implemented here — left for Phase 2).
The column type is ``LargeBinary`` to accommodate any symmetric cipher
output (AES-GCM ciphertext + nonce + tag).
"""

from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from strata.db.base import Base
from strata.utils import create_uuid, utcnow


class SmbCredential(Base):
    """Per-user SMB connection credential.

    One row per (user, host, share) combination.  A user may have credentials
    for multiple shares.

    Attributes:
        id: UUID primary key.
        user_id: FK → ``core_users.id`` ON DELETE CASCADE.
            No FK to ``jwt_auth_users`` — auth-backend-agnostic by design.
        host: Hostname or IP address of the SMB server.
        share: Share name on that server, e.g. ``"documents"``.
        domain: Windows domain, empty string if not applicable.
        smb_username: Username for the SMB connection (may differ from the
            Strata login name).
        encrypted_password: AES-GCM encrypted password blob.  ``None`` until
            the user saves credentials.
        created_at: UTC timestamp of row creation.
        updated_at: UTC timestamp of last credential update.
    """

    __tablename__ = "smb_storage_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=create_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        # FK to the platform identity table — no coupling to jwt_auth.
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    share: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    smb_username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    def __repr__(self) -> str:
        return (
            f"<SmbCredential id={self.id!r} user_id={self.user_id!r} "
            f"host={self.host!r} share={self.share!r}>"
        )
