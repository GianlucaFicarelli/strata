"""Abstract storage backend interface for Strata."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class FileEntry(BaseModel):
    """Metadata for a single file or directory entry.

    Attributes:
        name: Bare filename, e.g. ``"report.docx"``.
        path: Backend-relative path, e.g. ``"/docs/report.docx"``.
        is_dir: ``True`` if this entry is a directory.
        size: File size in bytes.  ``None`` for directories.
        modified: Last-modified time as a POSIX timestamp.  ``None`` if
            the backend does not expose modification times.
        mime: MIME type string, e.g. ``"image/png"``.  ``None`` if
            unknown or not applicable.

    """

    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified: float | None = None
    mime: str | None = None


class StorageBackend(ABC):
    """Abstract interface that every storage backend must implement.

    Paths passed to all methods are backend-relative and always begin
    with ``"/"``, e.g. ``"/photos/cat.jpg"``.  Backends are responsible
    for translating these paths to whatever addressing scheme they use
    internally (filesystem paths, S3 keys, SFTP paths, etc.).

    Attributes:
        id: Unique snake_case identifier used as the ``?backend=`` query
            parameter value, e.g. ``"s3"``.
        name: Human-readable display name shown in the UI picker.

    """

    id: str = ""
    name: str = ""

    @abstractmethod
    async def list(self, path: str) -> list[FileEntry]:
        """List the contents of a directory.

        Args:
            path: Backend-relative directory path.

        Returns:
            A list of ``FileEntry`` objects sorted directories-first,
            then alphabetically by name.

        Raises:
            HTTPException: 404 if the path does not exist; 400 if the
                path is not a directory.

        """
        ...

    @abstractmethod
    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Return an async byte-stream for the given file.

        Args:
            path: Backend-relative file path.

        Returns:
            An async generator that yields ``bytes`` chunks.

        Raises:
            HTTPException: 404 if the file does not exist.

        """
        ...

    @abstractmethod
    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Write a byte-stream to the given path, creating it if needed.

        Args:
            path: Backend-relative destination path.
            stream: Async generator providing the file's bytes.

        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file or directory (recursively).

        Args:
            path: Backend-relative path to delete.

        Raises:
            HTTPException: 404 if the path does not exist.

        """
        ...

    @abstractmethod
    async def mkdir(self, path: str) -> None:
        """Create a directory, including any missing parents.

        Args:
            path: Backend-relative path of the directory to create.

        """
        ...

    @abstractmethod
    async def move(self, src: str, dst: str) -> None:
        """Move or rename a file or directory.

        Args:
            src: Backend-relative source path.
            dst: Backend-relative destination path.

        Raises:
            HTTPException: 404 if ``src`` does not exist.

        """
        ...

    def describe(self) -> dict:
        """Return a JSON-serialisable summary of this backend.

        Used by ``GET /api/backends`` to advertise available backends to
        the frontend.

        Returns:
            A dict with at least ``"id"`` and ``"name"`` keys.

        """
        return {"id": self.id, "name": self.name}
