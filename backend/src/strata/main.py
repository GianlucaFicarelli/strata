"""Strata application entry point.

Assembles the FastAPI application, discovers plugins, registers storage
backends, and mounts static assets.

Database lifecycle
------------------
1. The async engine and session factory are created in :func:`lifespan` from
   ``STRATA_DB_URL``.
2. Plugin registration runs — each DB-aware plugin calls
   ``registry.db.add(MyDbContributor())`` to declare its tables.
3. Migrations run for every registered :class:`~strata.plugins.protocols.DbContributor`
   that provides a ``migrations_dir``.
4. The engine and session factory are stored in ``request.state`` so that
   the :data:`~strata.dependencies.AsyncSessionDep` ``Depends`` can yield
   a session to any route, including those added by plugins.
5. On shutdown the engine is disposed cleanly.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from strata.api.files import router as files_router
from strata.config import settings
from strata.db.plugin import CoreUsersDbContributor
from strata.db.session import create_engine, create_session_factory
from strata.db.utils import run_migrations
from strata.dependencies import StorageRegistryDep
from strata.plugins.loader import PluginLoader
from strata.plugins.registry import PluginRegistry

L = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[dict[str, Any]]:
    # Database setup
    engine = create_engine(settings.DB_URL, echo=settings.DB_ECHO)
    session_factory = create_session_factory(engine)

    plugin_registry = PluginRegistry()
    plugin_loader = PluginLoader()

    # Register core DB contributor first (before any plugin)
    plugin_registry.db.add(CoreUsersDbContributor())

    # Plugin discovery & registration
    await plugin_loader.load_and_register(
        registry=plugin_registry,
        enabled=settings.ENABLED_PLUGINS,
    )

    # Mount plugin routers after load_and_register so all RouteProviders are registered
    for router in plugin_registry.routes.all_routers():
        app.include_router(router)

    # Run DB migrations for every registered contributor
    for contributor in plugin_registry.db.all():
        try:
            L.warning("Running migration for contributor %r", type(contributor).__name__)
            await run_migrations(engine, contributor.migrations_dir)
        except Exception:
            L.exception(
                "Migrations failed for contributor %r — continuing startup.",
                type(contributor).__name__,
            )

    yield {
        "plugin_registry": plugin_registry,
        "plugin_loader": plugin_loader,
        "db_engine": engine,
        "db_session_factory": session_factory,
    }

    # Shutdown
    await plugin_loader.shutdown_all()
    await engine.dispose()
    L.info("Database engine disposed.")


app = FastAPI(
    title="Strata",
    version="0.1.0",
    description="A plugin-based file browser with swappable storage backends.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production via STRATA_CORS_ORIGINS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files_router)


@app.get("/api/backends", tags=["meta"])
def list_backends(storage_registry: StorageRegistryDep) -> list[dict]:
    """Return metadata for every registered storage backend.

    The frontend uses this to populate the backend picker dropdown.

    Returns:
        A list of dicts, one per registered ``StorageBackend``.

    """
    return [b.describe() for b in storage_registry.all()]


@app.get("/api/plugins", tags=["meta"])
def list_plugins(request: Request) -> list[dict]:
    """Return metadata for every loaded plugin.

    The frontend uses this to dynamically import each plugin's JS module
    and to know which file extensions each plugin handles.

    Returns:
        A list of dicts produced by ``BackendPlugin.describe()``.

    """
    plugin_loader: PluginLoader = request.state.plugin_loader
    return [p.describe() for p in plugin_loader.get_loaded_plugins()]


frontend_dist = settings.ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
