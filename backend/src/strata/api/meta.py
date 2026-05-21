"""Meta endpoints: plugin list and backend list."""

from fastapi import APIRouter, Request

from strata.dependencies.auth import OptionalCurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageRegistryDep, StorageTemplateRegistryDep
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
    storage_registry: StorageRegistryDep,
    template_registry: StorageTemplateRegistryDep,
    session: AsyncSessionDep,
    current_user: OptionalCurrentUserDep,
) -> list[StorageMeta]:
    """Return all storage backends available to the requesting user.

    Returns:
    - Directly registered (raw) backends from ``StorageRegistry``.
    - Admin-created instances that are ready for this user (is_enabled + all
      required user_editable fields filled).  Requires authentication.
    """
    result: list[StorageMeta] = [
        StorageMeta(id=b.describe().id, name=b.describe().name) for b in storage_registry.all()
    ]

    if current_user is not None:
        ready = await service.list_ready_backends_for_user(
            session,
            user_id=current_user.id,
            username=current_user.username,
            template_registry=template_registry,
        )
        for inst, backend in ready:
            result.append(service.backend_to_storage_meta(inst, backend))

    return result
