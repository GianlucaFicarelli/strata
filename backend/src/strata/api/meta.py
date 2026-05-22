"""Meta endpoints: plugin list and backend list."""

from fastapi import APIRouter, Request

from strata.dependencies.auth import OptionalCurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageTemplateRegistryDep
from strata.plugins.loader import PluginLoader
from strata.schemas.common import PluginMeta, StorageMeta
from strata.storage import service

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/plugins")
def list_plugins(request: Request) -> list[PluginMeta]:
    """Return metadata for every loaded plugin."""
    plugin_loader: PluginLoader = request.state.plugin_loader
    return [p.describe() for p in plugin_loader.get_loaded_plugins()]


@router.get("/backends")
async def list_backends(
    template_registry: StorageTemplateRegistryDep,
    session: AsyncSessionDep,
    current_user: OptionalCurrentUserDep,
) -> list[StorageMeta]:
    """Return storage backends available to the requesting user.

    Returns only admin-created instances that are fully ready for the current
    user: the instance must be admin-enabled, the user must have enabled it,
    and all required user-editable fields must be filled.

    Unauthenticated requests always receive an empty list.
    """
    if current_user is None:
        return []

    ready = await service.list_ready_backends_for_user(
        session,
        user_id=current_user.id,
        username=current_user.username,
        template_registry=template_registry,
    )
    return [service.backend_to_storage_meta(inst, backend) for inst, backend in ready]
