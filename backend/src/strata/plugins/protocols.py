"""Typed protocols defining each plugin capability in Strata.

Each protocol represents one extension point.  A plugin contributes to an
extension point by passing a conforming object to the appropriate ``add``
method on :class:`~strata.plugins.registry.PluginRegistry` inside its
:meth:`~strata.plugins.base.BackendPlugin.register` method.

Protocols are used for *static* type-checking only (pyright, mypy).
Runtime dispatch is handled by the registry itself.

Extension points
----------------
:class:`StorageBackend`
    Provides access to a storage system (filesystem, S3, SMB, …).
:class:`StorageTemplate`
    Blueprint for admin-configurable storage instances.  The admin creates
    instances; the core constructs backends at request time.
:class:`FileHandler`
    Provides a frontend viewer or editor for specific file extensions.
:class:`RouteProvider`
    Contributes FastAPI routes mounted at application startup.
:class:`AuthProvider`
    Provides an authentication method.  Exactly one may be active at a time.
    The plugin owns login/logout routes and credential verification.  Session
    management (cookie, Redis) is handled entirely by the core.
:class:`SearchProvider`
    Provides full-text or metadata search over a storage backend.
:class:`ThumbProvider`
    Generates thumbnail images for files on demand.
:class:`DbContributor`
    Contributes ORM tables and Alembic migrations to the shared database.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import MetaData

from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry
from strata.schemas.search import SearchResult


@dataclass(frozen=True)
class InstanceContext:
    """Runtime context passed to ``StorageTemplate.create()``.

    Carries the resolved user identity so that template fields such as
    ``/home/{username}`` can be expanded before the backend is constructed.

    Attributes:
        user_id: The ``core_users.id`` UUID of the requesting user.
        username: The login name of the requesting user as known to the active
            auth provider (from ``AuthUser.username``).
    """

    user_id: str
    username: str

    def expand(self, template: str) -> str:
        """Expand ``{user_id}`` and ``{username}`` placeholders in *template*.

        Args:
            template: String that may contain ``{username}`` or ``{user_id}``.

        Returns:
            String with all known placeholders substituted.
        """
        return template.replace("{user_id}", self.user_id).replace("{username}", self.username)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for objects that provide access to a storage system.

    All paths are backend-relative strings starting with ``"/"``, e.g.
    ``"/photos/cat.jpg"``.  Implementations translate these to whatever
    addressing scheme the underlying system uses (filesystem paths, S3 keys,
    SMB UNC paths, etc.).

    Attributes:
        id: Unique identifier used as the ``?backend=`` query parameter value.
        name: Human-readable display name shown in the UI backend picker.
    """

    id: str
    name: str

    async def list(self, path: str) -> list[FileEntry]:
        """List the contents of a directory."""
        ...

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Return an async byte-stream for a file."""
        ...

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        """Write a byte-stream to a path, creating it if necessary."""
        ...

    async def delete(self, path: str) -> None:
        """Delete a file or directory (recursively for directories)."""
        ...

    async def mkdir(self, path: str) -> None:
        """Create a directory, including any missing parents."""
        ...

    async def move(self, src: str, dst: str) -> None:
        """Move or rename a file or directory."""
        ...

    def describe(self) -> StorageMeta:
        """Return a summary of this backend for the backend picker."""
        ...


@runtime_checkable
class StorageTemplate(Protocol):
    """Protocol for plugin-registered storage blueprints.

    A ``StorageTemplate`` describes a class of storage configuration.  The
    admin creates one or more *instances* from a template (via the admin UI),
    and the core constructs a :class:`StorageBackend` at request time by
    resolving the instance config against the requesting user's context.

    Attributes:
        plugin_id: Must match the plugin's entry-point name, e.g.
            ``"storage_local"``.  Used as the FK in ``core_storage_instances``.
        display_name: Human-readable name shown in the admin template picker.
        description: One-line description.
        config_schema: The Pydantic model class describing the admin-level
            configuration.  Fields support ``json_schema_extra`` flags:

            - ``"secret": True`` — encrypted at rest; masked in GET responses.
            - ``"template": True`` — may contain ``{username}`` / ``{user_id}``
              placeholders expanded at request time.
            - ``"user_editable": True`` — user may override via self-service UI.
    """

    plugin_id: str
    display_name: str
    description: str
    config_schema: type[BaseModel]

    def create(
        self,
        config: BaseModel,
        context: InstanceContext,
    ) -> StorageBackend:
        """Construct a :class:`StorageBackend` from a resolved config.

        Args:
            config: Validated instance of :attr:`config_schema` with all
                admin-level fields set.  Secret fields are already decrypted.
                Template fields are NOT yet expanded — call
                ``context.expand(value)`` on fields marked ``template=True``.
            context: Runtime user context for template variable expansion.

        Returns:
            A ready-to-use :class:`StorageBackend` scoped to this request.
        """
        ...


@runtime_checkable
class FileHandler(Protocol):
    """Protocol for objects that handle specific file types in the frontend."""

    handles: list[str]
    frontend_module: str


@runtime_checkable
class RouteProvider(Protocol):
    """Protocol for objects that contribute FastAPI routes to the application."""

    def get_router(self) -> APIRouter:
        """Return a FastAPI ``APIRouter`` containing this provider's routes."""
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Protocol for objects that contribute an authentication method.

    Exactly one ``AuthProvider`` may be registered at a time (enforced by
    :class:`~strata.plugins.registry.AuthRegistry` at startup).

    The provider is responsible for:
    - Verifying credentials (username/password, OIDC code exchange, etc.)
    - Creating users in ``core_users`` on first login (for federated providers)
    - Contributing login/logout routes via :class:`RouteProvider`
    - Calling :class:`~strata.sessions.service.SessionService` to create and
      destroy sessions after credential verification

    The provider does **not** manage cookies, tokens, or session storage —
    those are owned entirely by the core.

    Attributes:
        id: Unique snake_case identifier, e.g. ``"auth_local"``.
        name: Human-readable display name, e.g. ``"Local accounts"``.
    """

    id: str
    name: str

    def describe(self) -> dict[str, Any]:
        """Return provider metadata consumed by ``GET /api/auth/providers``.

        The frontend uses this to determine which login UI to render.  Must
        include at minimum ``"id"`` and ``"name"``.

        Returns:
            Dict of metadata fields for this provider.
        """
        ...


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol for objects that provide search over a storage backend."""

    backend_id: str

    async def search(
        self,
        query: str,
        path: str = "/",
        *,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search for files matching *query* under *path*."""
        ...

    async def index(self, entry: FileEntry, content: AsyncIterator[bytes]) -> None:
        """Index a file so that it appears in future search results."""
        ...

    async def deindex(self, path: str) -> None:
        """Remove a file from the search index."""
        ...


@runtime_checkable
class ThumbProvider(Protocol):
    """Protocol for objects that generate thumbnail images."""

    def can_handle(self, mime: str) -> bool:
        """Return ``True`` if this provider can thumbnail files of *mime*."""
        ...

    async def generate(
        self,
        stream: AsyncIterator[bytes],
        *,
        width: int = 256,
        height: int = 256,
    ) -> bytes:
        """Generate a thumbnail from a file byte-stream."""
        ...


@runtime_checkable
class DbContributor(Protocol):
    """Protocol for plugins that contribute database tables."""

    metadata: MetaData
    migrations_dir: Path
