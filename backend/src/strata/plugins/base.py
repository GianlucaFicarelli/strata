"""Base class for all Strata plugins."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

    from strata.core.storage.base import StorageBackend


class BackendPlugin:
    """Abstract base class that every Strata plugin must subclass.

    A plugin may provide any combination of:
    - Extra API routes (``get_router``)
    - A storage backend (``get_storage_backend``)
    - A frontend ES module (``get_frontend_assets``)

    Attributes:
        id: Unique snake_case identifier, e.g. ``"collabora"``.
        name: Human-readable display name.
        version: SemVer string.
        description: One-line description shown in the plugin list.
        handles: File extensions this plugin can preview or process,
            e.g. ``[".docx", ".xlsx"]``. Used by the frontend to route
            files to the correct plugin without loading every JS module
            first. Empty list means the plugin does not handle specific
            file types.

    """

    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    handles: list[str] = []  # noqa: RUF012

    def get_router(self) -> APIRouter | None:
        """Return an APIRouter whose routes will be mounted at startup.

        Returns:
            A FastAPI ``APIRouter`` instance, or ``None`` if the plugin
            does not add any server-side routes.

        """
        return None

    def get_storage_backend(self) -> StorageBackend | None:
        """Return a ``StorageBackend`` instance if this plugin provides one.

        The returned backend is registered automatically at startup and
        becomes addressable via ``?backend=<id>`` on every file endpoint.

        Returns:
            A ``StorageBackend`` subclass instance, or ``None``.

        """
        return None

    def get_frontend_assets(self) -> dict[str, str]:
        """Return the URL of the plugin's frontend ES module.

        The module must export a ``register(registry)`` function.  It is
        loaded dynamically by the shell at startup.

        Returns:
            A dict with at least a ``"module"`` key pointing to the JS
            entry point served by the backend, e.g.
            ``{"module": "/api/plugins/foo/assets/main.js"}``.

        """
        return {"module": f"/api/plugins/{self.id}/assets/main.js"}

    def get_capabilities(self) -> list[str]:
        """Return a list of capability tags for this plugin.

        Well-known values: ``"storage"``, ``"preview"``, ``"editor"``,
        ``"auth"``.  The list is informational and used by the frontend
        to categorise plugins.

        Returns:
            A list of capability strings.

        """
        return []

    def describe(self) -> dict:
        """Return a JSON-serialisable summary of this plugin.

        Called by ``GET /api/plugins`` to advertise the plugin to the
        frontend shell.

        Returns:
            A dict containing id, name, version, description,
            capabilities, handles, and assets.

        """
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": self.get_capabilities(),
            "handles": self.handles,
            "assets": self.get_frontend_assets(),
        }

    async def on_startup(self) -> None:
        """Called once after the plugin is loaded at application startup."""

    async def on_shutdown(self) -> None:
        """Called once when the application is shutting down."""
