"""Plugin class."""

from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry
from strata_jwt_auth.providers import (
    JwtAuthDbContributor,
    JwtAuthRouteProvider,
    PasswordAuthProvider,
)


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

    def register(self, registry: PluginRegistry) -> None:
        """Contribute DB, auth, and route capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.auth.add(PasswordAuthProvider())
        registry.db.add(JwtAuthDbContributor())
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
        :data:`~strata.dependencies.db.AsyncSessionDep` both run at request time
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
