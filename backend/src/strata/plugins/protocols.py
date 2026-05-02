"""Typed protocols defining the contract for each plugin capability.

Each protocol corresponds to one extension point in the system.  A plugin
contributes to an extension point by passing a conforming object to the
appropriate method on :class:`~strata.plugins.registry.PluginRegistry`
inside its :meth:`~strata.plugins.base.BackendPlugin.register` method.

Protocols are used for *static* type checking only (pyright, mypy).  They
are **not** used for runtime ``isinstance`` checks — registration is
explicit and self-describing.

Extension points
----------------
- :class:`StorageBackend` — a storage backend accessible via ``?backend=<id>``
- :class:`FileHandler` — a frontend viewer/editor for specific file extensions
- :class:`RouteProvider` — extra FastAPI routes mounted at startup
- :class:`FrontendAssets` — a JavaScript ES module loaded by the shell
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastapi import APIRouter

from pydantic import BaseModel


# ── Shared data models ────────────────────────────────────────────────────────


class FileEntry(BaseModel):
    """Metadata for a single file or directory entry returned by a storage backend.

    Attributes:
        name: Bare filename, e.g. ``"report.docx"``.
        path: Backend-relative path, e.g. ``"/docs/report.docx"``.
        is_dir: ``True`` if this entry represents a directory.
        size: File size in bytes.  ``None`` for directories or when unknown.
        modified: Last-modified time as a POSIX timestamp.  ``None`` if the
            backend does not expose modification times.
        mime: MIME type string, e.g. ``"image/png"``.  ``None`` if unknown.
    """

    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified: float | None = None
    mime: str | None = None


# ── Capability protocols ──────────────────────────────────────────────────────


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for objects that provide access to a storage system.

    All paths are backend-relative strings that begin with ``"/"``, e.g.
    ``"/photos/cat.jpg"``.  Implementations translate these to whatever
    addressing scheme the underlying system uses (filesystem paths, S3
    object keys, SFTP paths, etc.).

    Attributes:
        id: Unique snake_case identifier used as the ``?backend=`` query
            parameter value, e.g. ``"s3"``.
        name: Human-readable display name shown in the UI backend picker.
    """

    id: str
    name: str

    async def list(self, path: str) -> list[FileEntry]:
        """List the contents of a directory.

        Args:
            path: Backend-relative directory path.

        Returns:
            Entries sorted directories-first, then alphabetically by name.

        Raises:
            HTTPException: 404 if *path* does not exist; 400 if it is not
                a directory.
        """
        ...

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Return an async byte-stream for a file.

        Args:
            path: Backend-relative file path.

        Returns:
            An async generator that yields ``bytes`` chunks.

        Raises:
            HTTPException: 404 if the file does not exist.
        """
        ...

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Write a byte-stream to a path, creating it if necessary.

        Args:
            path: Backend-relative destination path.
            stream: Async generator providing the file's bytes.
        """
        ...

    async def delete(self, path: str) -> None:
        """Delete a file or directory (recursively for directories).

        Args:
            path: Backend-relative path to delete.

        Raises:
            HTTPException: 404 if *path* does not exist.
        """
        ...

    async def mkdir(self, path: str) -> None:
        """Create a directory, including any missing parents.

        Args:
            path: Backend-relative path of the directory to create.
        """
        ...

    async def move(self, src: str, dst: str) -> None:
        """Move or rename a file or directory.

        Args:
            src: Backend-relative source path.
            dst: Backend-relative destination path.

        Raises:
            HTTPException: 404 if *src* does not exist.
        """
        ...

    def describe(self) -> dict[str, object]:
        """Return a JSON-serialisable summary of this backend.

        Used by ``GET /api/backends`` to advertise available backends to
        the frontend UI.

        Returns:
            A dict with at least ``"id"`` and ``"name"`` keys.
        """
        ...


@runtime_checkable
class FileHandler(Protocol):
    """Protocol for objects that handle specific file types in the frontend.

    A ``FileHandler`` declares which file extensions it can render and
    provides the URL of the JavaScript ES module that implements the UI.
    The module must export a ``register(registry)`` function.

    A plugin may also expose additional API routes (e.g. a thumbnail
    endpoint or a WOPI host) by *also* contributing a :class:`RouteProvider`
    to the registry inside the same ``register()`` call.

    Attributes:
        handles: File extensions this handler covers, lower-cased and
            including the leading dot, e.g. ``[".docx", ".xlsx"]``.
        frontend_module: Server-relative URL of the JS ES module,
            e.g. ``"/api/plugins/image_preview/assets/main.js"``.
    """

    handles: list[str]
    frontend_module: str


@runtime_checkable
class RouteProvider(Protocol):
    """Protocol for objects that contribute FastAPI routes to the application.

    The router returned by :meth:`get_router` is mounted onto the FastAPI
    application at startup.  Use this for plugin-specific API endpoints such
    as thumbnail generators, WOPI hosts, or any other custom HTTP handler.
    """

    def get_router(self) -> APIRouter:
        """Return a FastAPI ``APIRouter`` containing this plugin's routes.

        Returns:
            A configured ``APIRouter`` instance.
        """
        ...