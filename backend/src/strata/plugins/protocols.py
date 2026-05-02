"""Typed protocols defining each plugin capability in Strata.

Each protocol represents one extension point.  A plugin contributes to an
extension point by passing a conforming object to the appropriate ``add``
method on :class:`~strata.plugins.registry.PluginRegistry` inside its
:meth:`~strata.plugins.base.BackendPlugin.register` method.

Protocols are used for *static* type-checking only (pyright, mypy).  Runtime
dispatch is handled by the registry itself — no ``isinstance`` checks are
needed in application code.

Extension points
----------------
:class:`StorageBackend`
    Provides access to a storage system (filesystem, S3, SMB, …).
:class:`FileHandler`
    Provides a frontend viewer or editor for specific file extensions.
:class:`RouteProvider`
    Contributes FastAPI routes mounted at application startup.
:class:`AuthProvider`
    Provides an authentication method (password, OAuth, LDAP, …).
:class:`SearchProvider`
    Provides full-text or metadata search over a storage backend.
:class:`ThumbProvider`
    Generates thumbnail images for files on demand.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi import APIRouter


# ── Shared data models ────────────────────────────────────────────────────────


class FileEntry(BaseModel):
    """Metadata for a single file or directory entry.

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


class AuthUser(BaseModel):
    """Minimal representation of an authenticated user.

    Attributes:
        id: Opaque unique identifier for the user.
        username: Display name or email address.
        is_admin: ``True`` if the user has administrative privileges.
    """

    id: str
    username: str
    is_admin: bool = False


class SearchResult(BaseModel):
    """A single result returned by a search provider.

    Attributes:
        entry: The matching file entry.
        score: Relevance score in the range ``[0.0, 1.0]``.  Higher is more
            relevant.  ``None`` if the provider does not score results.
        snippet: A short excerpt from the file showing the match in context.
            ``None`` if the provider does not support snippets.
    """

    entry: FileEntry
    score: float | None = None
    snippet: str | None = None


# ── Capability protocols ──────────────────────────────────────────────────────


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for objects that provide access to a storage system.

    All paths are backend-relative strings starting with ``"/"``, e.g.
    ``"/photos/cat.jpg"``.  Implementations translate these to whatever
    addressing scheme the underlying system uses (filesystem paths, S3 keys,
    SMB UNC paths, etc.).

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
            An async generator yielding ``bytes`` chunks.

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

    def describe(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of this backend.

        Used by ``GET /api/backends`` to populate the frontend backend picker.

        Returns:
            A dict with at least ``"id"`` and ``"name"`` keys.
        """
        ...


@runtime_checkable
class FileHandler(Protocol):
    """Protocol for objects that handle specific file types in the frontend.

    A ``FileHandler`` declares which file extensions it can render and
    provides the server-relative URL of the JavaScript ES module that
    implements the viewer or editor component.  The module must export a
    ``register(registry)`` function.

    Attributes:
        handles: Lower-cased extensions including the leading dot, e.g.
            ``[".docx", ".xlsx"]``.
        frontend_module: Server-relative URL of the JS ES module, e.g.
            ``"/api/plugins/image_preview/assets/main.js"``.
    """

    handles: list[str]
    frontend_module: str


@runtime_checkable
class RouteProvider(Protocol):
    """Protocol for objects that contribute FastAPI routes to the application.

    The router returned by :meth:`get_router` is mounted onto the FastAPI
    application at startup.  Use this for plugin-specific API endpoints such
    as thumbnail generators, WOPI hosts, or custom webhooks.
    """

    def get_router(self) -> APIRouter:
        """Return a FastAPI ``APIRouter`` containing this provider's routes.

        Returns:
            A configured ``fastapi.APIRouter`` instance.
        """
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Protocol for objects that authenticate users.

    An ``AuthProvider`` verifies credentials and returns an
    :class:`AuthUser`.  Multiple providers can coexist (e.g. local password
    auth alongside LDAP); the registry tries them in registration order.

    Attributes:
        id: Unique snake_case identifier, e.g. ``"password"`` or ``"ldap"``.
        name: Human-readable name shown in the login UI.
    """

    id: str
    name: str

    async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
        """Attempt to authenticate a user from the given credentials.

        Args:
            credentials: A dict of credential fields, e.g.
                ``{"username": "alice", "password": "secret"}``.  The exact
                keys depend on the provider.

        Returns:
            An :class:`AuthUser` if authentication succeeded, or ``None``
            if the credentials were not recognised by this provider.

        Raises:
            HTTPException: 401 if credentials were recognised but invalid
                (wrong password). Return ``None`` — do not raise — if the
                provider simply does not handle these credentials.
        """
        ...


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol for objects that provide search over a storage backend.

    A ``SearchProvider`` is tied to a specific storage backend (matched by
    :attr:`backend_id`) and indexes or queries that backend's contents.

    Attributes:
        backend_id: The ``id`` of the :class:`StorageBackend` this provider
            searches, e.g. ``"local"``.
    """

    backend_id: str

    async def search(
        self,
        query: str,
        path: str = "/",
        *,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search for files matching *query* under *path*.

        Args:
            query: Free-text or structured query string.
            path: Backend-relative directory to restrict the search to.
                Defaults to the root.
            limit: Maximum number of results to return.

        Returns:
            A list of :class:`SearchResult` objects sorted by descending
            relevance score.
        """
        ...

    async def index(self, entry: FileEntry, content: AsyncIterator[bytes]) -> None:
        """Index a file so that it appears in future search results.

        Called automatically by the file write pipeline when search indexing
        is enabled.  Implementations should be idempotent.

        Args:
            entry: Metadata of the file to index.
            content: Async byte-stream of the file's content.
        """
        ...

    async def deindex(self, path: str) -> None:
        """Remove a file from the search index.

        Called automatically when a file is deleted or moved.

        Args:
            path: Backend-relative path of the file to remove from the index.
        """
        ...


@runtime_checkable
class ThumbProvider(Protocol):
    """Protocol for objects that generate thumbnail images.

    A ``ThumbProvider`` accepts a file byte-stream and returns a resized
    JPEG or PNG thumbnail.  Multiple providers can be registered; the
    registry selects the first one whose :meth:`can_handle` returns ``True``
    for a given MIME type.
    """

    def can_handle(self, mime: str) -> bool:
        """Return ``True`` if this provider can thumbnail files of *mime*.

        Args:
            mime: MIME type string, e.g. ``"image/png"`` or
                ``"application/pdf"``.

        Returns:
            ``True`` if this provider handles the given MIME type.
        """
        ...

    async def generate(
        self,
        stream: AsyncIterator[bytes],
        *,
        width: int = 256,
        height: int = 256,
    ) -> bytes:
        """Generate a thumbnail from a file byte-stream.

        Args:
            stream: Async byte-stream of the source file.
            width: Maximum thumbnail width in pixels.
            height: Maximum thumbnail height in pixels.

        Returns:
            Raw bytes of the thumbnail image (JPEG or PNG).
        """
        ...
