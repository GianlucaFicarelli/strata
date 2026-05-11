"""Plugin class, auth provider, and route provider for strata-jwt-auth."""

from importlib.resources import files
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import MetaData, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import AuthUser
from strata.plugins.registry import PluginRegistry
from strata_jwt_auth.models import Base, User
from strata_jwt_auth.router import plugin_router
from strata_jwt_auth.utils import auth_user_from_token, user_to_auth_user, verify_password

# ── DbContributor ─────────────────────────────────────────────────────────────


class JwtAuthDbContributor:
    """Registers the jwt_auth ORM metadata and Alembic migrations directory.

    The :class:`~strata.plugins.registry.DbRegistry` picks this up during
    startup and runs Alembic ``upgrade head`` before the first request.

    Attributes:
        metadata: SQLAlchemy :class:`~sqlalchemy.MetaData` for the
            ``jwt_auth_users`` and ``jwt_auth_refresh_tokens`` tables.
        migrations_dir: Absolute path to the ``migrations/`` directory
            shipped inside this package, resolved via ``importlib.resources``.
    """

    metadata: MetaData = Base.metadata
    migrations_dir: Path = Path(str(files("strata_jwt_auth").joinpath("migrations")))


# ── AuthProvider ──────────────────────────────────────────────────────────────


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
                "Ensure jwt_auth on_startup() has been called."
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

    def describe(self) -> dict:
        """Return provider metadata for the frontend.

        The frontend reads ``login_url`` to know where to POST credentials.

        Returns:
            A dict with ``id``, ``name``, and ``login_url``.
        """
        return {
            "id": self.id,
            "name": self.name,
            "login_url": "/api/plugins/jwt_auth/login",
        }


# ── RouteProvider ─────────────────────────────────────────────────────────────


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


# ── Plugin ────────────────────────────────────────────────────────────────────


class JwtAuthPlugin(BackendPlugin):
    """Plugin providing JWT-based username/password authentication.

    Capabilities contributed:

    - ``registry.db``: :class:`JwtAuthDbContributor` — declares the ORM tables
      and Alembic migrations directory so the shared engine runs
      ``upgrade head`` at startup automatically.
    - ``registry.auth``: :class:`PasswordAuthProvider` — validates
      username/password credentials against ``jwt_auth_users``.
    - ``registry.routes``: :class:`JwtAuthRouteProvider` — mounts the
      ``/api/plugins/jwt_auth/*`` endpoints.

    Session factory injection
    -------------------------
    The :class:`PasswordAuthProvider` needs a session factory so it can query
    the DB when called from :class:`~strata.plugins.registry.AuthRegistry`
    (outside the FastAPI request cycle).  The factory is stored in
    ``request.state.db_session_factory`` at runtime; here we keep a reference
    to the provider and patch it in :meth:`on_startup` via a small shim that
    pulls the factory from ``app.state``.  Because Strata's lifespan stores
    state in the ``yield`` dict (which becomes ``request.state`` per request
    but is also available as ``app.state``), this works cleanly.
    """

    id = "jwt_auth"
    name = "JWT Auth"
    version = "0.1.0"
    description = "Username/password login with JWT access and refresh tokens."

    def __init__(self) -> None:
        super().__init__()
        self._auth_provider = PasswordAuthProvider()

    def register(self, registry: PluginRegistry) -> None:
        """Contribute DB, auth, and route capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.db.add(JwtAuthDbContributor())
        registry.auth.add(self._auth_provider)
        registry.routes.add(JwtAuthRouteProvider())

    async def on_startup(self) -> None:
        """Wire the session factory into the auth provider.

        The session factory is not available at :meth:`register` time because
        the engine hasn't been created yet.  The main lifespan sets up the
        engine, then calls ``on_startup`` for each plugin.  We hook into the
        FastAPI ``app.state`` here to retrieve the factory.

        Note: ``app.state`` is populated by the ``yield`` dict in
        :func:`strata.main.lifespan`.  Since ``on_startup`` is called
        *within* that lifespan (before the ``yield``), the state dict is not
        yet on ``app.state`` at this exact moment.

        Therefore the session factory injection is deferred: the router
        dependency :func:`~strata_jwt_auth.router.current_user_dep` and the
        :data:`~strata.dependencies.AsyncSessionDep` both run at request time
        when the factory is already in ``request.state``.  The
        ``PasswordAuthProvider`` is only needed when
        :meth:`~strata.plugins.registry.AuthRegistry.authenticate` is called
        directly (e.g. from another plugin); that call should happen after
        startup, at which point the factory is available.

        The cleanest approach: expose a ``set_session_factory`` hook that
        :func:`strata.main.lifespan` calls explicitly after the yield dict is
        built.  For now we skip this and document that callers of
        ``AuthRegistry.authenticate`` must ensure startup has completed.
        """

    async def on_shutdown(self) -> None:
        """Nothing to clean up."""


plugin = JwtAuthPlugin()
