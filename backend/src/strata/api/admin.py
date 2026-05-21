"""Admin API for managing storage templates and instances.

All routes require an authenticated admin user (``is_admin=True``).

Routes
------
GET  /api/admin/storage/templates         — list all registered templates + JSON schemas
GET  /api/admin/storage/instances         — list all instances
POST /api/admin/storage/instances         — create an instance
GET  /api/admin/storage/instances/{id}    — get one instance (secrets masked)
PUT  /api/admin/storage/instances/{id}    — update an instance
DELETE /api/admin/storage/instances/{id} — delete an instance
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageTemplateRegistryDep
from strata.schemas.auth import AuthUser
from strata.schemas.storage import (
    StorageInstanceCreate,
    StorageInstanceResponse,
    StorageInstanceUpdate,
    StorageTemplateSchema,
)
from strata.storage import service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user: CurrentUserDep) -> AuthUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminDep = Annotated[AuthUser, Depends(_require_admin)]


# ── Templates ─────────────────────────────────────────────────────────────────


@router.get("/storage/templates")
def list_templates(
    _: AdminDep,
    template_registry: StorageTemplateRegistryDep,
) -> list[StorageTemplateSchema]:
    """List all registered storage templates with their JSON schemas."""
    return [
        StorageTemplateSchema(
            plugin_id=t.plugin_id,
            display_name=t.display_name,
            description=t.description,
            config_schema=t.config_schema.model_json_schema(),
        )
        for t in template_registry.all()
    ]


# ── Instances ─────────────────────────────────────────────────────────────────


@router.get("/storage/instances")
async def list_instances(
    _: AdminDep,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> list[StorageInstanceResponse]:
    """List all admin-created storage instances."""
    instances = await service.list_instances(session)
    result: list[StorageInstanceResponse] = []
    for inst in instances:
        tmpl = template_registry.get(inst.plugin_id)
        if tmpl is None:
            continue
        result.append(StorageInstanceResponse(**service.instance_to_response(inst, tmpl)))
    return result


@router.post("/storage/instances", status_code=status.HTTP_201_CREATED)
async def create_instance(
    _: AdminDep,
    body: StorageInstanceCreate,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> StorageInstanceResponse:
    """Create a new storage instance from a registered template."""
    tmpl = template_registry.get(body.plugin_id)
    if tmpl is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown template plugin_id {body.plugin_id!r}",
        )
    instance = await service.create_instance(
        session,
        plugin_id=body.plugin_id,
        instance_name=body.instance_name,
        raw_config=body.config,
        template=tmpl,
    )
    return StorageInstanceResponse(**service.instance_to_response(instance, tmpl))


@router.get("/storage/instances/{instance_id}")
async def get_instance(
    instance_id: str,
    _: AdminDep,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> StorageInstanceResponse:
    """Get one storage instance (secret fields masked)."""
    instance = await service.get_instance(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    tmpl = template_registry.get(instance.plugin_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found for this instance")
    return StorageInstanceResponse(**service.instance_to_response(instance, tmpl))


@router.put("/storage/instances/{instance_id}")
async def update_instance(
    instance_id: str,
    body: StorageInstanceUpdate,
    _: AdminDep,
    session: AsyncSessionDep,
    template_registry: StorageTemplateRegistryDep,
) -> StorageInstanceResponse:
    """Update a storage instance. Secret fields may be sent as '********' to keep existing."""
    instance = await service.get_instance(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    tmpl = template_registry.get(instance.plugin_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found for this instance")
    instance = await service.update_instance(
        session,
        instance=instance,
        template=tmpl,
        instance_name=body.instance_name,
        raw_config=body.config,
        is_enabled=body.is_enabled,
    )
    return StorageInstanceResponse(**service.instance_to_response(instance, tmpl))


@router.delete("/storage/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: str,
    _: AdminDep,
    session: AsyncSessionDep,
) -> None:
    """Delete a storage instance and all associated user configs."""
    instance = await service.get_instance(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    await session.delete(instance)
    await session.flush()
