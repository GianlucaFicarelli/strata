"""Meta endpoints: plugin list."""

from fastapi import APIRouter, Request

from strata.plugins.loader import PluginLoader
from strata.schemas.common import PluginMeta

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/plugins")
def list_plugins(request: Request) -> list[PluginMeta]:
    """Return metadata for every loaded plugin."""
    plugin_loader: PluginLoader = request.state.plugin_loader
    return [p.describe() for p in plugin_loader.get_loaded_plugins()]
