"""Strata application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from strata.api.admin import router as admin_router
from strata.api.auth import router as auth_router
from strata.api.files import router as files_router
from strata.api.meta import router as meta_router
from strata.api.user_storage import router as user_storage_router
from strata.config import settings
from strata.db.plugin import CoreUsersDbContributor
from strata.db.session import create_engine, create_session_factory
from strata.db.utils import run_migrations
from strata.plugins.loader import PluginLoader
from strata.plugins.registry import PluginRegistry

L = logging.getLogger(__name__)


def _validate_encryption_key(registry: PluginRegistry) -> None:
    """Fail fast if any template declares secret fields but ENCRYPTION_KEY is unset."""
    if not registry.storage_templates.has_any_secret_fields():
        return
    if not settings.ENCRYPTION_KEY:
        raise RuntimeError(
            "STRATA_ENCRYPTION_KEY must be set: one or more registered storage templates "
            "declare secret fields that require encryption at rest. "
            "Generate a key with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[dict[str, Any]]:
    engine = create_engine(settings.DB_URL, echo=settings.DB_ECHO)
    session_factory = create_session_factory(engine)

    plugin_registry = PluginRegistry()
    plugin_loader = PluginLoader()

    plugin_registry.db.add(CoreUsersDbContributor())

    await plugin_loader.load_and_register(
        registry=plugin_registry,
        enabled=settings.ENABLED_PLUGINS,
    )

    # Validate encryption key after all templates are registered
    _validate_encryption_key(plugin_registry)

    for router in plugin_registry.routes.all_routers():
        app.include_router(router)

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

    await plugin_loader.shutdown_all()
    await engine.dispose()
    L.info("Database engine disposed.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta_router)
app.include_router(auth_router)
app.include_router(files_router)
app.include_router(admin_router)
app.include_router(user_storage_router)

frontend_dist = settings.ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
