"""Local filesystem storage backend for Strata."""

import contextlib
import mimetypes
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
from fastapi import HTTPException

from strata.core.storage.base import FileEntry, StorageBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

#: Root directory exposed by this backend.  Override via the
#: ``STRATA_LOCAL_ROOT`` environment variable.
_ROOT: Path = Path(os.environ.get("STRATA_LOCAL_ROOT", Path.home())).resolve()

#: Read chunk size in bytes.
_CHUNK: int = 64 * 1024


def _safe(rel: str) -> Path:
    """Resolve *rel* to an absolute path and assert it stays inside ``_ROOT``.

    Args:
        rel: Backend-relative path string, e.g. ``"/docs/report.pdf"``.

    Returns:
        The resolved absolute ``Path``.

    Raises:
        HTTPException: 403 if the resolved path escapes ``_ROOT``.

    """
    target = (_ROOT / rel.lstrip("/")).resolve()
    if not target.is_relative_to(_ROOT):
        raise HTTPException(status_code=403, detail="Path escapes storage root")
    return target


def _entry(p: Path) -> FileEntry:
    """Build a ``FileEntry`` from a ``Path`` relative to ``_ROOT``.

    Args:
        p: Absolute path that must be inside ``_ROOT``.

    Returns:
        A populated ``FileEntry`` instance.

    """
    stat = p.stat()
    rel = "/" + str(p.relative_to(_ROOT))
    mime: str | None = None
    if p.is_file():
        mime, _ = mimetypes.guess_type(p.name)
    return FileEntry(
        name=p.name,
        path=rel,
        is_dir=p.is_dir(),
        size=stat.st_size if p.is_file() else None,
        modified=stat.st_mtime,
        mime=mime,
    )


class LocalStorageBackend(StorageBackend):
    """Storage backend that reads and writes the local filesystem.

    The accessible tree is rooted at ``_ROOT`` (``$STRATA_LOCAL_ROOT``
    or the current user's home directory).  All path traversal outside
    the root is rejected with HTTP 403.
    """

    id: str = "local"
    name: str = "Local Filesystem"

    async def list(self, path: str) -> list[FileEntry]:
        """List directory contents sorted directories-first, then by name.

        Args:
            path: Backend-relative directory path.

        Returns:
            Sorted list of ``FileEntry`` objects.

        Raises:
            HTTPException: 404 if *path* does not exist; 400 if it is
                not a directory.

        """
        target = _safe(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail="Not a directory")

        entries: list[FileEntry] = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            with contextlib.suppress(PermissionError):
                entries.append(_entry(child))
        return entries

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream a file as async byte chunks.

        Args:
            path: Backend-relative file path.

        Returns:
            An async generator yielding ``bytes`` of up to ``_CHUNK``
            bytes each.

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
        """Write an async stream to disk, creating parent directories.

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


#: Singleton instance registered at startup.
local_storage: LocalStorageBackend = LocalStorageBackend()
