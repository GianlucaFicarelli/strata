"""SMB/CIFS network share storage backend plugin for Strata.

Contributes:

- :class:`~strata.plugins.protocols.StorageBackend`: accesses a Samba /
  Windows share via the SMB protocol.
- :class:`~strata.plugins.protocols.DbContributor`: declares the
  ``smb_storage_credentials`` table so per-user credentials can be stored.
  The ``user_id`` FK points at ``core_users.id`` — no dependency on any
  specific auth plugin.

Entry point::

    [project.entry-points."strata.plugins"]
    smb_storage = "strata_smb_storage:plugin"

Configuration (service-level fallback — used when no per-user credential row
exists for the requesting user):

    STRATA_SMB_HOST      Hostname or IP of the SMB server.
    STRATA_SMB_SHARE     Share name, e.g. ``"documents"``.
    STRATA_SMB_USERNAME  SMB username.
    STRATA_SMB_PASSWORD  SMB password.
    STRATA_SMB_DOMAIN    Windows domain (default ``""``).
"""

import os
from collections.abc import AsyncIterator
from importlib.resources import files
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData

from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry
from strata.schemas.files import FileEntry
from strata_smb_storage.models import Base

# ── DbContributor ─────────────────────────────────────────────────────────────


class SmbStorageDbContributor:
    """Registers ``smb_storage_credentials`` and its Alembic migrations.

    Attributes:
        metadata: SQLAlchemy :class:`~sqlalchemy.MetaData` for this plugin.
        migrations_dir: Path to the ``migrations/`` directory inside the
            installed package, resolved via ``importlib.resources``.
    """

    metadata: MetaData = Base.metadata
    migrations_dir: Path = Path(str(files("strata_smb_storage").joinpath("migrations")))


# ── StorageBackend ────────────────────────────────────────────────────────────


class SmbStorageBackend:
    """Storage backend that accesses an SMB/CIFS network share.

    For now uses service-level credentials from environment variables.
    Phase 2 will load per-user credentials from ``smb_storage_credentials``
    via :data:`~strata.dependencies.db.AsyncSessionDep`.

    Attributes:
        id: ``"smb_storage"``
        name: ``"SMB / Network Share"``
    """

    id: str = "smb_storage"
    name: str = "SMB / Network Share"

    def __init__(self) -> None:
        self.host: str = os.environ.get("STRATA_SMB_HOST", "")
        self.share: str = os.environ.get("STRATA_SMB_SHARE", "")
        self.username: str = os.environ.get("STRATA_SMB_USERNAME", "")
        self.password: str = os.environ.get("STRATA_SMB_PASSWORD", "")
        self.domain: str = os.environ.get("STRATA_SMB_DOMAIN", "")

    def _unc(self, path: str) -> str:
        """Build a UNC path for *path* on this share.

        Args:
            path: Backend-relative path, e.g. ``"/reports/q1.xlsx"``.

        Returns:
            UNC path string, e.g. ``"\\\\server\\documents\\reports\\q1.xlsx"``.
        """
        parts = path.lstrip("/").replace("/", "\\")
        return f"\\\\{self.host}\\{self.share}\\{parts}"

    async def list(self, path: str) -> list[FileEntry]:
        """List contents of an SMB directory.

        Args:
            path: Backend-relative directory path.

        Returns:
            Sorted file entries.

        Todo:
            Use ``smbclient.scandir(self._unc(path))`` to iterate entries.
        """
        return []  # TODO: implement with smbclient

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream a file from the SMB share.

        Args:
            path: Backend-relative file path.

        Returns:
            Async generator yielding ``bytes`` chunks.

        Todo:
            Open with ``smbclient.open_file(self._unc(path), mode="rb")``
            and yield in chunks.
        """

        async def _stub() -> AsyncIterator[bytes]:
            yield b""  # TODO: implement with smbclient

        return _stub()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Write an async stream to a file on the SMB share.

        Args:
            path: Backend-relative destination path.
            stream: Async generator providing file bytes.

        Todo:
            Open with ``smbclient.open_file(self._unc(path), mode="wb")``
            and write chunks.
        """

    async def delete(self, path: str) -> None:
        """Delete a file or directory from the SMB share.

        Args:
            path: Backend-relative path to remove.

        Todo:
            Use ``smbclient.remove`` for files or ``smbclient.rmdir`` /
            a recursive variant for directories.
        """

    async def mkdir(self, path: str) -> None:
        """Create a directory on the SMB share.

        Args:
            path: Backend-relative directory path to create.

        Todo:
            Use ``smbclient.makedirs(self._unc(path), exist_ok=True)``.
        """

    async def move(self, src: str, dst: str) -> None:
        """Rename or move a path on the SMB share.

        Args:
            src: Backend-relative source path.
            dst: Backend-relative destination path.

        Todo:
            Use ``smbclient.rename(self._unc(src), self._unc(dst))``.
        """

    def describe(self) -> dict[str, Any]:
        """Return backend metadata including host and share name.

        Returns:
            A dict with ``id``, ``name``, ``host``, and ``share`` keys.
            Password is intentionally omitted.
        """
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "share": self.share,
        }


class SmbStoragePlugin(BackendPlugin):
    """Plugin that registers the SMB network share storage backend.

    Capabilities contributed:

    - ``registry.storage``: :class:`SmbStorageBackend`
    - ``registry.db``: :class:`SmbStorageDbContributor` — declares
      ``smb_storage_credentials`` with ``user_id FK → core_users.id``.
    """

    id = "smb_storage"
    name = "SMB Storage"
    version = "0.1.0"
    description = "Samba / Windows network share storage with per-user credentials."

    def register(self, registry: PluginRegistry) -> None:
        """Register the SMB storage backend.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.db.add(SmbStorageDbContributor())
        registry.storage.add(SmbStorageBackend())


plugin = SmbStoragePlugin()
