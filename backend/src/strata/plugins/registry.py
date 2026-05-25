"""Plugin registry — the set of all extension points in Strata."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from strata.plugins.protocols import (
    AuthProvider,
    DbContributor,
    FileHandler,
    RouteProvider,
    SearchProvider,
    StorageBackend,
    StorageTemplate,
    ThumbProvider,
)
from strata.schemas.search import SearchResult

L = logging.getLogger(__name__)


class StorageRegistry:
    """Registry of available :class:`~strata.plugins.protocols.StorageBackend` instances."""

    def __init__(self) -> None:
        self._backends: dict[str, StorageBackend] = {}

    def add(self, backend: StorageBackend) -> None:
        if backend.id in self._backends:
            L.warning("Replacing already-registered storage backend %r", backend.id)
        self._backends[backend.id] = backend
        L.info("Registered storage backend %r (%s)", backend.id, backend.name)

    def get(self, backend_id: str) -> StorageBackend:
        try:
            return self._backends[backend_id]
        except KeyError:
            available = sorted(self._backends)
            raise HTTPException(
                status_code=400,
                detail=f"Unknown backend {backend_id!r}. Available: {available}",
            ) from None

    def all(self) -> list[StorageBackend]:
        return list(self._backends.values())


class StorageTemplateRegistry:
    """Registry of :class:`~strata.plugins.protocols.StorageTemplate` instances.

    Templates are registered by plugins at startup.  The admin creates
    instances from templates via the admin API.  At request time, the storage
    dependency resolves instance IDs by looking up the appropriate template
    and calling ``template.create(config, context)``.
    """

    def __init__(self) -> None:
        self._templates: dict[str, StorageTemplate] = {}

    def add(self, template: StorageTemplate) -> None:
        """Register a storage template.

        Args:
            template: A :class:`~strata.plugins.protocols.StorageTemplate`
                implementation to register.
        """
        if template.plugin_id in self._templates:
            L.warning("Replacing already-registered storage template %r", template.plugin_id)
        self._templates[template.plugin_id] = template
        L.info(
            "Registered storage template %r (%s)",
            template.plugin_id,
            template.display_name,
        )

    def get(self, plugin_id: str) -> StorageTemplate | None:
        """Return the template for *plugin_id*, or ``None``."""
        return self._templates.get(plugin_id)

    def all(self) -> list[StorageTemplate]:
        """Return every registered template in registration order."""
        return list(self._templates.values())

    def schema_for(self, plugin_id: str) -> dict[str, Any] | None:
        """Return the JSON Schema for a template's config model, or ``None``."""
        template = self.get(plugin_id)
        if template is None:
            return None
        return template.config_schema.model_json_schema()

    def has_any_secret_fields(self) -> bool:
        """Return ``True`` if any registered template has secret config fields."""
        for template in self._templates.values():
            schema = template.config_schema.model_json_schema()
            for prop in schema.get("properties", {}).values():
                if prop.get("secret"):
                    return True
        return False

    def validate_config(self, plugin_id: str, config: dict[str, Any]) -> BaseModel:
        """Validate *config* against the template's schema.

        Args:
            plugin_id: Template identifier.
            config: Raw config dict from the request body.

        Returns:
            Validated Pydantic model instance.

        Raises:
            HTTPException: 400 if *plugin_id* is unknown or validation fails.
        """
        template = self.get(plugin_id)
        if template is None:
            raise HTTPException(status_code=400, detail=f"Unknown template {plugin_id!r}")
        try:
            return template.config_schema.model_validate(config)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


class RouteRegistry:
    """Registry of :class:`~strata.plugins.protocols.RouteProvider` instances."""

    def __init__(self) -> None:
        self._providers: list[RouteProvider] = []

    def add(self, provider: RouteProvider) -> None:
        self._providers.append(provider)
        L.info("Registered route provider: %r", type(provider).__name__)

    def all_routers(self) -> list[APIRouter]:
        return [p.get_router() for p in self._providers]


class FileHandlerRegistry:
    """Registry of :class:`~strata.plugins.protocols.FileHandler` instances."""

    def __init__(self) -> None:
        self._handlers: list[FileHandler] = []

    def add(self, handler: FileHandler) -> None:
        self._handlers.append(handler)
        L.info("Registered file handler %r for: %s", type(handler).__name__, handler.handles)

    def all(self) -> list[FileHandler]:
        return list(self._handlers)

    def for_extension(self, ext: str) -> FileHandler | None:
        return next((h for h in self._handlers if ext in h.handles), None)


class AuthRegistry:
    """Registry for the active :class:`~strata.plugins.protocols.AuthProvider`.

    Strata supports exactly one auth provider at a time.  Attempting to
    register a second provider raises ``RuntimeError`` at startup so
    misconfiguration is caught immediately rather than at first login.

    The provider is responsible for credential verification and contributing
    login/logout routes.  Session management (Redis storage, HttpOnly cookie)
    is handled entirely by the core.
    """

    def __init__(self) -> None:
        self._provider: AuthProvider | None = None

    def add(self, provider: AuthProvider) -> None:
        """Register the auth provider.

        Args:
            provider: The :class:`~strata.plugins.protocols.AuthProvider` to
                register.

        Raises:
            RuntimeError: If a provider is already registered (only one
                auth provider may be active at a time).
        """
        if self._provider is not None:
            raise RuntimeError(
                f"Cannot register auth provider {provider.id!r}: "
                f"{self._provider.id!r} is already registered. "
                "Strata supports exactly one auth provider at a time. "
                "Check STRATA_ENABLED_PLUGINS."
            )
        self._provider = provider
        L.info("Registered auth provider %r (%s)", provider.id, provider.name)

    def get(self) -> AuthProvider | None:
        """Return the active provider, or ``None`` if none is registered."""
        return self._provider

    def all(self) -> list[AuthProvider]:
        """Return a list of zero or one providers (for API compatibility)."""
        return [self._provider] if self._provider is not None else []


class SearchRegistry:
    """Registry of :class:`~strata.plugins.protocols.SearchProvider` instances."""

    def __init__(self) -> None:
        self._providers: dict[str, SearchProvider] = {}

    def add(self, provider: SearchProvider) -> None:
        if provider.backend_id in self._providers:
            L.warning("Replacing search provider for backend %r", provider.backend_id)
        self._providers[provider.backend_id] = provider
        L.info(
            "Registered search provider %r for backend %r",
            type(provider).__name__,
            provider.backend_id,
        )

    def get(self, backend_id: str) -> SearchProvider | None:
        return self._providers.get(backend_id)

    async def search(
        self,
        backend_id: str,
        query: str,
        path: str = "/",
        *,
        limit: int = 50,
    ) -> list[SearchResult]:
        provider = self.get(backend_id)
        if provider is None:
            return []
        return await provider.search(query, path, limit=limit)


class ThumbRegistry:
    """Registry of :class:`~strata.plugins.protocols.ThumbProvider` instances."""

    def __init__(self) -> None:
        self._providers: list[ThumbProvider] = []

    def add(self, provider: ThumbProvider) -> None:
        self._providers.append(provider)
        L.info("Registered thumb provider: %r", type(provider).__name__)

    def for_mime(self, mime: str) -> ThumbProvider | None:
        return next((p for p in self._providers if p.can_handle(mime)), None)

    async def generate(
        self,
        mime: str,
        stream: AsyncIterator[bytes],
        *,
        width: int = 256,
        height: int = 256,
    ) -> bytes | None:
        provider = self.for_mime(mime)
        if provider is None:
            return None
        return await provider.generate(stream, width=width, height=height)


class DbRegistry:
    """Registry of :class:`~strata.plugins.protocols.DbContributor` instances."""

    def __init__(self) -> None:
        self._contributors: list[DbContributor] = []

    def add(self, contributor: DbContributor) -> None:
        self._contributors.append(contributor)
        L.info(
            "Registered DB contributor %r (%d tables)",
            type(contributor).__name__,
            len(contributor.metadata.tables),
        )

    def all(self) -> list[DbContributor]:
        return list(self._contributors)


@dataclass
class PluginRegistry:
    """Composite registry holding all extension point sub-registries."""

    storage: StorageRegistry = field(default_factory=StorageRegistry)
    storage_templates: StorageTemplateRegistry = field(default_factory=StorageTemplateRegistry)
    routes: RouteRegistry = field(default_factory=RouteRegistry)
    file_handlers: FileHandlerRegistry = field(default_factory=FileHandlerRegistry)
    auth: AuthRegistry = field(default_factory=AuthRegistry)
    search: SearchRegistry = field(default_factory=SearchRegistry)
    thumbs: ThumbRegistry = field(default_factory=ThumbRegistry)
    db: DbRegistry = field(default_factory=DbRegistry)
