from pathlib import Path

from fastapi import APIRouter

from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import AuthUser
from strata.plugins.registry import PluginRegistry
from strata_jwt_auth.config import settings
from strata_jwt_auth.router import plugin_router


class PasswordAuthProvider:
    """Authenticates users with a username/password credential pair.

    Implements :class:`~strata.plugins.protocols.AuthProvider`.

    Attributes:
        id: ``"password"``
        name: ``"Username & Password"``
    """

    id: str = "password"
    name: str = "Username & Password"

    async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
        """Validate username/password credentials against the user database.

        Args:
            credentials: Dict with ``"username"`` and ``"password"`` keys.

        Returns:
            An :class:`~strata.plugins.protocols.AuthUser` on success, or
            ``None`` if the credentials dict does not contain the expected
            keys (letting other providers try).

        Raises:
            HTTPException: 401 if username/password are present but wrong.

        Todo:
            Fetch user from DB, verify password hash, return ``AuthUser``.
        """
        if "username" not in credentials or "password" not in credentials:
            return None
        # TODO: fetch from DB, verify hash, return AuthUser or raise 401.
        return None


class JwtAuthRouteProvider:
    """Contributes the register / login / logout API routes.

    Implements :class:`~strata.plugins.protocols.RouteProvider`.
    """

    def get_router(self) -> APIRouter:
        """Return the JWT auth API router.

        Returns:
            The configured ``fastapi.APIRouter``.
        """
        return plugin_router


class JwtAuthPlugin(BackendPlugin):
    """Plugin providing JWT-based username/password authentication.

    Capabilities contributed:

    - ``registry.auth``: :class:`PasswordAuthProvider`
    - ``registry.routes``: :class:`JwtAuthRouteProvider`
    """

    id = "jwt_auth"
    name = "JWT Auth"
    version = "0.1.0"
    description = "Username/password login with JWT access tokens."

    def register(self, registry: PluginRegistry) -> None:
        """Contribute auth capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.auth.add(PasswordAuthProvider())
        registry.routes.add(JwtAuthRouteProvider())

    async def on_startup(self) -> None:
        """Create the auth database directory if it does not exist.

        Todo:
            Run Alembic migrations to create/update the ``users`` table.
        """
        db_path = settings.AUTH_DB_URL.replace("sqlite+aiosqlite:///", "")
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


plugin = JwtAuthPlugin()
