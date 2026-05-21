"""User self-service storage configuration API.

Users manage their personal config for each admin-created storage instance.

Routes
------
GET   /api/storage/instances               — list all instances with user's config state
GET   /api/storage/instances/{id}/me       — get user's config for one instance
PATCH /api/storage/instances/{id}/me       — update user's config (enable/disable + editable fields)
"""

from fastapi import APIRouter, HTTPException, status

from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageTemplateRegistryDep
from strata.schemas.storage import UserStorageConfigResponse, UserStorageConfigUpdate
from strata.storage import service

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("/instances")
async def list_user_instances(
    current_user: CurrentUserDep,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> list[UserStorageConfigResponse]:
    """List all admin-enabled instances with this user's config state.

    Returns every admin-enabled instance regardless of whether the user has
    configured it yet, so the user can discover and enable new instances.
    """
    instances = await service.list_instances(session)
    user_cfgs = {
        uc.instance_id: uc for uc in await service.list_user_configs(session, current_user.id)
    }
    result: list[UserStorageConfigResponse] = []
    for inst in instances:
        if not inst.is_enabled:
            continue
        tmpl = template_registry.get(inst.plugin_id)
        if tmpl is None:
            continue
        user_cfg = user_cfgs.get(inst.id)
        result.append(
            UserStorageConfigResponse(**service.user_config_to_response(inst, user_cfg, tmpl))
        )
    return result


@router.get("/instances/{instance_id}/me")
async def get_user_instance_config(
    instance_id: str,
    current_user: CurrentUserDep,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> UserStorageConfigResponse:
    """Get this user's config state for one instance."""
    instance = await service.get_instance(session, instance_id)
    if instance is None or not instance.is_enabled:
        raise HTTPException(status_code=404, detail="Instance not found")
    tmpl = template_registry.get(instance.plugin_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    user_cfg = await service.get_user_config(session, instance_id, current_user.id)
    return UserStorageConfigResponse(**service.user_config_to_response(instance, user_cfg, tmpl))


@router.patch("/instances/{instance_id}/me", status_code=status.HTTP_200_OK)
async def update_user_instance_config(
    instance_id: str,
    body: UserStorageConfigUpdate,
    current_user: CurrentUserDep,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> UserStorageConfigResponse:
    """Update this user's config for one instance.

    - Set ``is_enabled`` to ``true`` to make the instance visible in the
      backend picker (it will only appear once all required fields are filled).
    - Provide ``config`` with only the ``user_editable`` fields to set;
      non-editable fields are silently ignored.
    """
    instance = await service.get_instance(session, instance_id)
    if instance is None or not instance.is_enabled:
        raise HTTPException(status_code=404, detail="Instance not found")
    tmpl = template_registry.get(instance.plugin_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    user_cfg = await service.upsert_user_config(
        session,
        instance=instance,
        user_id=current_user.id,
        template=tmpl,
        is_enabled=body.is_enabled,
        raw_user_config=body.config,
    )
    return UserStorageConfigResponse(**service.user_config_to_response(instance, user_cfg, tmpl))
