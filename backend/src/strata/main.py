"""Strata application entry point.

Assembles the FastAPI application, discovers plugins, registers storage
backends, and mounts static assets.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from strata.config import settings
from strata.core.files import router as files_router
from strata.core.storage import registry as storage_registry
from strata.plugins.loader import discover_plugins, get_plugins

app = FastAPI(
    title="Strata",
    version="0.1.0",
    description="A plugin-based file browser with swappable storage backends.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production via STRATA_CORS_ORIGINS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core routes ───────────────────────────────────────────────────────────────

app.include_router(files_router)


@app.get("/api/backends", tags=["meta"])
def list_backends() -> list[dict]:
    """Return metadata for every registered storage backend.

    The frontend uses this to populate the backend picker dropdown.

    Returns:
        A list of dicts, one per registered ``StorageBackend``.

    """
    return [b.describe() for b in storage_registry.get_all()]


@app.get("/api/plugins", tags=["meta"])
def list_plugins() -> list[dict]:
    """Return metadata for every loaded plugin.

    The frontend uses this to dynamically import each plugin's JS module
    and to know which file extensions each plugin handles.

    Returns:
        A list of dicts produced by ``BackendPlugin.describe()``.

    """
    return [p.describe() for p in get_plugins()]


# ── Startup / shutdown ────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup() -> None:
    """Discover plugins and wire them into the running application.

    For each plugin this function:

    1. Registers its storage backend (if any) with the storage registry.
    2. Mounts its API router (if any) onto the FastAPI app.
    3. Serves its frontend assets as static files under
       ``/api/plugins/<id>/assets/``.
    4. Calls ``plugin.on_startup()``.
    """
    plugins = discover_plugins("plugins_enabled")

    for p in plugins:
        # 1. Register storage backend
        storage_backend = p.get_storage_backend()
        if storage_backend is not None:
            storage_registry.register(storage_backend)

        # 2. Mount plugin API routes
        router = p.get_router()
        if router is not None:
            app.include_router(router)

        # 3. Serve plugin frontend assets
        assets_dir = Path(__file__).parent / "plugins_enabled" / p.id / "frontend"
        if assets_dir.exists():
            app.mount(
                f"/api/plugins/{p.id}/assets",
                StaticFiles(directory=str(assets_dir)),
                name=f"plugin-{p.id}-assets",
            )

        # 4. Plugin lifecycle hook
        await p.on_startup()


@app.on_event("shutdown")
async def shutdown() -> None:
    """Notify all plugins that the application is shutting down."""
    for p in get_plugins():
        await p.on_shutdown()


# ── Serve built frontend ──────────────────────────────────────────────────────

frontend_dist = settings.ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
