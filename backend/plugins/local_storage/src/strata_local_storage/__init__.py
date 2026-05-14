"""Local filesystem storage backend plugin for Strata.

Registers a :class:`~strata.plugins.protocols.StorageBackend` that reads and
writes the local filesystem, rooted at the directory configured by
``STRATA_LOCAL_ROOT`` (defaults to the current user's home directory).

All path traversal outside the configured root is rejected with HTTP 403.

Entry point::

    [project.entry-points."strata.plugins"]
    local_storage = "strata_local_storage:plugin"

Configuration:
    STRATA_LOCAL_ROOT: Absolute path to the directory exposed as the
        storage root.  Defaults to the current user's home directory.
"""

import mimetypes
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles
from fastapi import HTTPException

from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry
from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry

_ROOT: Path = Path(os.environ.get("STRATA_LOCAL_ROOT", Path.home())).resolve()
_CHUNK: int = 64 * 1024


def _safe(rel: str) -> Path:
    """Resolve *rel* and assert it stays inside ``_ROOT``.

    Args:
        rel: Backend-relative path string.

    Returns:
        Resolved absolute ``Path``.

    Raises:
        HTTPException: 403 if the resolved path escapes ``_ROOT``.
    """
    target = (_ROOT / rel.lstrip("/")).resolve()
    if not target.is_relative_to(_ROOT):
        raise HTTPException(status_code=403, detail="Path escapes storage root")
    return target


def _to_entry(p: Path) -> FileEntry:
    """Build a :class:`~strata.plugins.protocols.FileEntry` from a ``Path``.

    Args:
        p: Absolute path inside ``_ROOT``.

    Returns:
        A populated :class:`~strata.plugins.protocols.FileEntry`.
    """
    stat = p.stat()
    mime: str | None = None
    if p.is_file():
        mime, _ = mimetypes.guess_type(p.name)
    return FileEntry(
        name=p.name,
        path="/" + str(p.relative_to(_ROOT)),
        is_dir=p.is_dir(),
        size=stat.st_size if p.is_file() else None,
        modified=stat.st_mtime,
        mime=mime,
    )


class LocalStorageBackend:
    """Storage backend that reads and writes the local filesystem.

    Implements the :class:`~strata.plugins.protocols.StorageBackend` protocol.

    Attributes:
        id: ``"local_storage"``
        name: ``"Local Filesystem"``
    """

    id: str = "local_storage"
    name: str = "Local Filesystem"

    async def list(self, path: str) -> list[FileEntry]:
        """List directory contents sorted directories-first, then by name.

        Args:
            path: Backend-relative directory path.

        Returns:
            Sorted list of :class:`~strata.plugins.protocols.FileEntry` objects.

        Raises:
            HTTPException: 404 if *path* does not exist; 400 if not a directory.
        """
        target = _safe(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail="Not a directory")
        entries: list[FileEntry] = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                entries.append(_to_entry(child))
            except PermissionError:
                pass
        return entries

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream a file as async byte chunks.

        Args:
            path: Backend-relative file path.

        Returns:
            An async generator yielding up to ``_CHUNK`` bytes at a time.

        Raises:
            HTTPException: 404 if the file does not exist.
        """
        target = _safe(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        async def _gen() -> AsyncIterator[bytes]:
            async with aiofiles.open(target, "rb") as fh:
                while chunk := await fh.read(_CHUNK):
                    yield chunk

        return _gen()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Write an async stream to disk, creating parent directories as needed.

        Args:
            path: Backend-relative destination path.
            stream: Async generator providing file bytes.
        """
        target = _safe(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "wb") as fh:
            async for chunk in stream:
                await fh.write(chunk)

    async def delete(self, path: str) -> None:
        """Delete a file or directory tree.

        Args:
            path: Backend-relative path to remove.

        Raises:
            HTTPException: 404 if *path* does not exist.
        """
        target = _safe(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Not found")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    async def mkdir(self, path: str) -> None:
        """Create a directory and any missing parents.

        Args:
            path: Backend-relative path of the directory to create.
        """
        _safe(path).mkdir(parents=True, exist_ok=True)

    async def move(self, src: str, dst: str) -> None:
        """Move or rename a path.

        Args:
            src: Backend-relative source path.
            dst: Backend-relative destination path.
        """
        shutil.move(str(_safe(src)), str(_safe(dst)))

    def describe(self) -> StorageMeta:
        """Return backend metadata including the configured root path.

        Returns:
            A dict with ``id``, ``name``, and ``root`` keys.
        """
        return StorageMeta(
            id=self.id,
            name=self.name,
            # root=str(_ROOT),
        )


class LocalStoragePlugin(BackendPlugin):
    """Plugin that registers the local filesystem storage backend.

    Capabilities contributed:

    - ``registry.storage``: :class:`LocalStorageBackend`
    """

    id = "local_storage"
    name = "Local Storage"
    version = "0.1.0"
    description = "Exposes the local filesystem as a storage backend."

    def register(self, registry: PluginRegistry) -> None:
        """Register the local filesystem storage backend.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.storage.add(LocalStorageBackend())


plugin = LocalStoragePlugin()
