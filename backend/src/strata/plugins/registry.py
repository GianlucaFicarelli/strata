"""Plugin registry — the set of all extension points in Strata.

A single :class:`PluginRegistry` instance is created at application startup
and passed to every plugin's :meth:`~strata.plugins.base.BackendPlugin.register`
method.  Each plugin calls the typed ``add`` methods on the appropriate
sub-registry to contribute its capabilities.

The application reads from these registries when:

- wiring FastAPI routes (``RouteRegistry``)
- resolving ``?backend=<id>`` query parameters (``StorageRegistry``)
- building the frontend plugin manifest (``FileHandlerRegistry``)
- selecting a thumbnail generator (``ThumbRegistry``)
- running a search query (``SearchRegistry``)
- authenticating a login request (``AuthRegistry``)
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException

from strata.plugins.protocols import (
    AuthProvider,
    AuthUser,
    FileHandler,
    RouteProvider,
    SearchProvider,
    SearchResult,
    StorageBackend,
    ThumbProvider,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import APIRouter

L = logging.getLogger(__name__)


class StorageRegistry:
    """Registry of available :class:`~strata.plugins.protocols.StorageBackend` instances.

    Queried by the ``backend_dep`` FastAPI dependency to resolve
    ``?backend=<id>`` on every file endpoint.
    """

    def __init__(self) -> None:
        self._backends: dict[str, StorageBackend] = {}

    def add(self, backend: StorageBackend) -> None:
        """Register a storage backend.

        If a backend with the same :attr:`~StorageBackend.id` is already
        registered it will be replaced and a warning logged.

        Args:
            backend: A :class:`~strata.plugins.protocols.StorageBackend`
                implementation to register.
        """
        if backend.id in self._backends:
            L.warning("Replacing already-registered storage backend %r", backend.id)
        self._backends[backend.id] = backend
        L.info("Registered storage backend %r (%s)", backend.id, backend.name)

    def get(self, backend_id: str) -> StorageBackend:
        """Look up a backend by its :attr:`~StorageBackend.id`.

        Args:
            backend_id: The identifier to look up, e.g. ``"s3"``.

        Returns:
            The matching :class:`~strata.plugins.protocols.StorageBackend`.

        Raises:
            HTTPException: 400 if *backend_id* is not registered.
        """
        try:
            return self._backends[backend_id]
        except KeyError:
            available = sorted(self._backends)
            raise HTTPException(
                status_code=400,
                detail=f"Unknown backend {backend_id!r}. Available: {available}",
            ) from None

    def all(self) -> list[StorageBackend]:
        """Return every registered backend in registration order.

        Returns:
            A list of :class:`~strata.plugins.protocols.StorageBackend` instances.
        """
        return list(self._backends.values())


class RouteRegistry:
    """Registry of :class:`~strata.plugins.protocols.RouteProvider` instances.

    Routers are collected during plugin registration and mounted onto the
    FastAPI application in a single pass during startup.
    """

    def __init__(self) -> None:
        self._providers: list[RouteProvider] = []

    def add(self, provider: RouteProvider) -> None:
        """Register a route provider.

        Args:
            provider: A :class:`~strata.plugins.protocols.RouteProvider`
                whose router will be mounted at startup.
        """
        self._providers.append(provider)
        L.info("Registered route provider: %r", type(provider).__name__)

    def all_routers(self) -> list[APIRouter]:
        """Return all routers ready to be mounted onto the FastAPI app.

        Returns:
            A list of ``fastapi.APIRouter`` instances.
        """
        return [p.get_router() for p in self._providers]


class FileHandlerRegistry:
    """Registry of :class:`~strata.plugins.protocols.FileHandler` instances.

    The frontend shell reads the handler list from ``GET /api/plugins`` to
    know which JS module to load for each file extension.
    """

    def __init__(self) -> None:
        self._handlers: list[FileHandler] = []

    def add(self, handler: FileHandler) -> None:
        """Register a file handler.

        Args:
            handler: A :class:`~strata.plugins.protocols.FileHandler`
                implementation to register.
        """
        self._handlers.append(handler)
        L.info(
            "Registered file handler %r for: %s",
            type(handler).__name__,
            handler.handles,
        )

    def all(self) -> list[FileHandler]:
        """Return every registered file handler in registration order.

        Returns:
            A list of :class:`~strata.plugins.protocols.FileHandler` instances.
        """
        return list(self._handlers)

    def for_extension(self, ext: str) -> FileHandler | None:
        """Find the first handler that covers a given file extension.

        Args:
            ext: Lower-cased extension including the leading dot,
                e.g. ``".docx"``.

        Returns:
            The first matching handler, or ``None``.
        """
        return next((h for h in self._handlers if ext in h.handles), None)


class AuthRegistry:
    """Registry of :class:`~strata.plugins.protocols.AuthProvider` instances.

    Providers are tried in registration order; the first one that returns a
    non-``None`` :class:`~strata.plugins.protocols.AuthUser` wins.
    """

    def __init__(self) -> None:
        self._providers: list[AuthProvider] = []

    def add(self, provider: AuthProvider) -> None:
        """Register an authentication provider.

        Args:
            provider: A :class:`~strata.plugins.protocols.AuthProvider`
                implementation to register.
        """
        self._providers.append(provider)
        L.info("Registered auth provider %r (%s)", provider.id, provider.name)

    async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
        """Try each provider in order and return the first successful result.

        Args:
            credentials: A dict of credential fields forwarded to each
                provider's :meth:`~AuthProvider.authenticate` method.

        Returns:
            The authenticated :class:`~strata.plugins.protocols.AuthUser`, or
            ``None`` if no provider recognised the credentials.
        """
        for provider in self._providers:
            user = await provider.authenticate(credentials)
            if user is not None:
                return user
        return None

    def all(self) -> list[AuthProvider]:
        """Return every registered auth provider in registration order.

        Returns:
            A list of :class:`~strata.plugins.protocols.AuthProvider` instances.
        """
        return list(self._providers)


class SearchRegistry:
    """Registry of :class:`~strata.plugins.protocols.SearchProvider` instances.

    Each provider is associated with a specific storage backend via its
    :attr:`~SearchProvider.backend_id` attribute.
    """

    def __init__(self) -> None:
        self._providers: dict[str, SearchProvider] = {}

    def add(self, provider: SearchProvider) -> None:
        """Register a search provider.

        Args:
            provider: A :class:`~strata.plugins.protocols.SearchProvider`
                implementation.  Its :attr:`~SearchProvider.backend_id` must
                match the ``id`` of an already-registered
                :class:`~strata.plugins.protocols.StorageBackend`.
        """
        if provider.backend_id in self._providers:
            L.warning("Replacing search provider for backend %r", provider.backend_id)
        self._providers[provider.backend_id] = provider
        L.info(
            "Registered search provider %r for backend %r",
            type(provider).__name__,
            provider.backend_id,
        )

    def get(self, backend_id: str) -> SearchProvider | None:
        """Return the search provider for *backend_id*, or ``None``.

        Args:
            backend_id: The storage backend identifier to look up.

        Returns:
            The matching :class:`~strata.plugins.protocols.SearchProvider`,
            or ``None`` if no provider is registered for that backend.
        """
        return self._providers.get(backend_id)

    async def search(
        self,
        backend_id: str,
        query: str,
        path: str = "/",
        *,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Run a search query against the provider for *backend_id*.

        Args:
            backend_id: The storage backend to search.
            query: Free-text query string.
            path: Backend-relative directory to restrict the search to.
            limit: Maximum number of results to return.

        Returns:
            Search results, or an empty list if no provider is registered.
        """
        provider = self.get(backend_id)
        if provider is None:
            return []
        return await provider.search(query, path, limit=limit)


class ThumbRegistry:
    """Registry of :class:`~strata.plugins.protocols.ThumbProvider` instances.

    Providers are tried in registration order; the first one whose
    :meth:`~ThumbProvider.can_handle` returns ``True`` for a given MIME type
    is used to generate the thumbnail.
    """

    def __init__(self) -> None:
        self._providers: list[ThumbProvider] = []

    def add(self, provider: ThumbProvider) -> None:
        """Register a thumbnail provider.

        Args:
            provider: A :class:`~strata.plugins.protocols.ThumbProvider`
                implementation to register.
        """
        self._providers.append(provider)
        L.info("Registered thumb provider: %r", type(provider).__name__)

    def for_mime(self, mime: str) -> ThumbProvider | None:
        """Find the first provider that can thumbnail files of *mime*.

        Args:
            mime: MIME type string, e.g. ``"image/png"``.

        Returns:
            The first matching :class:`~strata.plugins.protocols.ThumbProvider`,
            or ``None`` if no provider handles this MIME type.
        """
        return next((p for p in self._providers if p.can_handle(mime)), None)

    async def generate(
        self,
        mime: str,
        stream: AsyncIterator[bytes],
        *,
        width: int = 256,
        height: int = 256,
    ) -> bytes | None:
        """Generate a thumbnail for a file, selecting the appropriate provider.

        Args:
            mime: MIME type of the source file.
            stream: Async byte-stream of the source file.
            width: Maximum thumbnail width in pixels.
            height: Maximum thumbnail height in pixels.

        Returns:
            Raw thumbnail bytes, or ``None`` if no provider handles *mime*.
        """
        provider = self.for_mime(mime)
        if provider is None:
            return None
        return await provider.generate(stream, width=width, height=height)


# ── Composite registry ────────────────────────────────────────────────────────


@dataclass
class PluginRegistry:
    """Composite registry passed to every plugin's ``register()`` method.

    Each field is a typed sub-registry for one category of extension point.
    Plugins call the appropriate ``add`` methods to contribute capabilities;
    the application reads from these registries to wire routes, resolve
    backends, build the plugin manifest, and dispatch requests.

    Attributes:
        storage: Registry of storage backends.
        routes: Registry of FastAPI route providers.
        file_handlers: Registry of frontend file viewers/editors.
        auth: Registry of authentication providers.
        search: Registry of search providers.
        thumbs: Registry of thumbnail generators.
    """

    storage: StorageRegistry = field(default_factory=StorageRegistry)
    routes: RouteRegistry = field(default_factory=RouteRegistry)
    file_handlers: FileHandlerRegistry = field(default_factory=FileHandlerRegistry)
    auth: AuthRegistry = field(default_factory=AuthRegistry)
    search: SearchRegistry = field(default_factory=SearchRegistry)
    thumbs: ThumbRegistry = field(default_factory=ThumbRegistry)
