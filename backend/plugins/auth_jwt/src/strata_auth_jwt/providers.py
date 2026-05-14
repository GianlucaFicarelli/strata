"""DB contributor, auth provider, and route provider."""

from importlib.resources import files
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import MetaData, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.plugins.protocols import DbContributor
from strata.schemas.auth import AuthUser
from strata_auth_jwt.models import Base
from strata_auth_jwt.router import plugin_router
from strata_auth_jwt.utils import User, auth_user_from_token, user_to_auth_user, verify_password


class JwtAuthDbContributor(DbContributor):
    """Registers the auth_jwt ORM metadata and Alembic migrations directory.

    The :class:`~strata.plugins.registry.DbRegistry` picks this up during
    startup and runs Alembic ``upgrade head`` before the first request.

    Attributes:
        metadata: SQLAlchemy :class:`~sqlalchemy.MetaData` for the
            ``auth_jwt_users`` and ``auth_jwt_refresh_tokens`` tables.
        migrations_dir: Absolute path to the ``migrations/`` directory
            shipped inside this package, resolved via ``importlib.resources``.
    """

    metadata: MetaData = Base.metadata
    migrations_dir: Path = Path(str(files("strata_auth_jwt").joinpath("migrations")))


class PasswordAuthProvider:
    """Authenticates users with a username/password credential pair.

    Implements :class:`~strata.plugins.protocols.AuthProvider`.

    The session factory is injected via :meth:`set_session_factory` during
    plugin startup (after the engine is available) so that
    :meth:`authenticate` can open its own session when called from the
    :class:`~strata.plugins.registry.AuthRegistry` outside the request cycle.

    Attributes:
        id: ``"password"``
        name: ``"Username & Password"``
    """

    id: str = "password"
    name: str = "Username & Password"

    def __init__(self) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def set_session_factory(self, factory: async_sessionmaker[AsyncSession]) -> None:
        """Inject the application session factory.

        Called by :class:`JwtAuthPlugin` once the engine is confirmed ready.

        Args:
            factory: The ``async_sessionmaker`` from ``request.state``.
        """
        self._session_factory = factory

    async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
        """Validate username/password against the database.

        Returns ``None`` (pass to next provider) if ``username`` or
        ``password`` keys are absent.  Raises 401 if they are present but
        wrong.

        Args:
            credentials: Dict with at least ``"username"`` and ``"password"``.

        Returns:
            An :class:`~strata.plugins.protocols.AuthUser` on success.

        Raises:
            HTTPException: 401 if credentials are recognised but invalid.
            RuntimeError: If called before :meth:`set_session_factory`.
        """
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            return None

        if self._session_factory is None:
            raise RuntimeError(
                "PasswordAuthProvider has no session factory. "
                "Ensure auth_jwt on_startup() has been called."
            )

        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.username == username))
            user: User | None = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_to_auth_user(user)

    async def verify_token(self, token: str) -> AuthUser | None:
        """Verify a JWT access token and return the corresponding user.

        This is the token-side of the auth protocol, called by the core
        ``require_current_user_dep`` dependency on every protected request.
        The core never imports JWT-specific code — it only calls this method.

        Args:
            token: Raw JWT string from the ``Authorization: Bearer`` header.

        Returns:
            An :class:`~strata.plugins.protocols.AuthUser` if the token is
            valid, or ``None`` if it is not a JWT we issued (so other
            providers get a chance).

        Raises:
            HTTPException: 401 if the token looks like ours but is
                invalid or expired.
        """
        return auth_user_from_token(token)

    def describe(self) -> dict[str, Any]:
        """Return provider metadata for the frontend.

        The frontend reads ``login_url`` to know where to POST credentials.

        Returns:
            A dict with ``id``, ``name``, and ``login_url``.
        """
        return {
            "id": self.id,
            "name": self.name,
            "login_url": "/api/plugins/auth_jwt/login",
        }


class JwtAuthRouteProvider:
    """Contributes the register / login / refresh / logout / me routes.

    Implements :class:`~strata.plugins.protocols.RouteProvider`.
    """

    def get_router(self) -> APIRouter:
        """Return the JWT auth router.

        Returns:
            The configured ``fastapi.APIRouter``.
        """
        return plugin_router
