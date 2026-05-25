"""auth_local — local username/password authentication plugin for Strata.

Provides invite-only account registration, Argon2id password hashing, and
session-cookie based authentication backed by the core Redis session service.

Entry point: ``auth_local = "strata_auth_local:plugin"``
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from strata.plugins.base import BackendPlugin

if TYPE_CHECKING:
    from strata.plugins.registry import PluginRegistry


class _AuthLocalProvider:
    """AuthProvider implementation for local username/password auth."""

    id: str = "auth_local"
    name: str = "Local accounts"

    def describe(self) -> dict[str, Any]:
        """Return metadata for ``GET /api/auth/providers``.

        Returns:
            Dict with ``id``, ``name``, and ``login_url`` for the frontend.
        """
        return {
            "id": self.id,
            "name": self.name,
            "login_url": "/api/plugins/auth_local/login",
        }


class _AuthLocalDbContributor:
    """DbContributor that registers auth_local_users and its migrations."""

    from strata_auth_local.models import Base as _LocalBase  # noqa: PLC0415

    metadata = _LocalBase.metadata
    migrations_dir: Path = Path(__file__).parent / "migrations"


class _AuthLocalRouteProvider:
    """RouteProvider that contributes login/logout/invite routes."""

    def get_router(self):  # type: ignore[return]
        from strata_auth_local.router import router  # noqa: PLC0415

        return router


class AuthLocalPlugin(BackendPlugin):
    """Strata plugin for local username/password authentication.

    Registers:
    - An :class:`AuthProvider` that advertises the local login endpoint.
    - A :class:`DbContributor` for the ``auth_local_users`` table.
    - A :class:`RouteProvider` for login, logout, and invite routes.
    """

    id = "auth_local"
    name = "Auth Local"
    version = "0.1.0"
    description = "Local username/password authentication with invite-only registration."

    def register(self, registry: "PluginRegistry") -> None:
        """Register auth provider, DB contributor, and route provider."""
        registry.auth.add(_AuthLocalProvider())
        registry.db.add(_AuthLocalDbContributor())
        registry.routes.add(_AuthLocalRouteProvider())


plugin = AuthLocalPlugin()
