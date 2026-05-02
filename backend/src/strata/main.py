"""Strata application entry point.

Assembles the FastAPI application, discovers plugins, registers storage
backends, and mounts static assets.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from strata.api.files import router as files_router
from strata.config import settings
from strata.dependencies import StorageRegistryDep
from strata.plugins.loader import PluginLoader
from strata.plugins.registry import PluginRegistry


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[dict[str, Any]]:
    plugin_registry = PluginRegistry()
    plugin_loader = PluginLoader()
    await plugin_loader.load_and_register(
        registry=plugin_registry,
        enabled=settings.ENABLED_PLUGINS,
    )
    yield {
        "plugin_registry": plugin_registry,
        "plugin_loader": plugin_loader,
    }
    await plugin_loader.shutdown_all()


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
