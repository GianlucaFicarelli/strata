"""Business logic for storage instance resolution and management."""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from strata.config import settings
from strata.crypto import decrypt_field, encrypt_field
from strata.db.models import CoreStorageInstance, CoreStorageUserConfig
from strata.plugins.protocols import InstanceContext, StorageBackend, StorageTemplate
from strata.plugins.registry import StorageTemplateRegistry
from strata.schemas.storage import ReadyBackendMeta
from strata.utils import create_uuid, utcnow

L = logging.getLogger(__name__)

_MASKED = "********"


def _field_flags(schema: dict[str, Any], field_name: str) -> dict[str, Any]:
    return schema.get("properties", {}).get(field_name, {})


def _is_secret(schema: dict[str, Any], field_name: str) -> bool:
    return bool(_field_flags(schema, field_name).get("secret"))


def _is_template_field(schema: dict[str, Any], field_name: str) -> bool:
    return bool(_field_flags(schema, field_name).get("template"))


def _is_user_editable(schema: dict[str, Any], field_name: str) -> bool:
    return bool(_field_flags(schema, field_name).get("user_editable"))


def _required_user_editable_fields(schema: dict[str, Any]) -> set[str]:
    required = set(schema.get("required", []))
    return {
        name
        for name, prop in schema.get("properties", {}).items()
        if prop.get("user_editable") and name in required
    }


def encrypt_config(raw_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw_config.items():
        if _is_secret(schema, k) and isinstance(v, str) and v and v != _MASKED:
            out[k] = encrypt_field(v, settings.ENCRYPTION_KEY)
        else:
            out[k] = v
    return out


def decrypt_config(stored_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in stored_config.items():
        if _is_secret(schema, k) and isinstance(v, str) and v:
            try:
                out[k] = decrypt_field(v, settings.ENCRYPTION_KEY)
            except ValueError:
                L.error("Failed to decrypt field %r", k)
                out[k] = ""
        else:
            out[k] = v
    return out


def mask_config(stored_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    return {k: (_MASKED if _is_secret(schema, k) and v else v) for k, v in stored_config.items()}


def is_instance_ready(
    instance: CoreStorageInstance,
    user_config: CoreStorageUserConfig | None,
    template: StorageTemplate,
) -> bool:
    if not instance.is_enabled:
        return False
    if user_config is None or not user_config.is_enabled:
        return False
    schema = template.config_schema.model_json_schema()
    required = _required_user_editable_fields(schema)
    if not required:
        return True
    user_cfg = json.loads(user_config.config_json)
    return all(user_cfg.get(f) for f in required)


def build_backend(
    instance: CoreStorageInstance,
    user_config: CoreStorageUserConfig | None,
    template: StorageTemplate,
    context: InstanceContext,
) -> StorageBackend:
    schema = template.config_schema.model_json_schema()
    admin_cfg = decrypt_config(json.loads(instance.config_json), schema)
    user_cfg = decrypt_config(json.loads(user_config.config_json), schema) if user_config else {}

    merged: dict[str, Any] = {**admin_cfg}
    for k, v in user_cfg.items():
        if _is_user_editable(schema, k):
            merged[k] = v

    for k, v in merged.items():
        if _is_template_field(schema, k) and isinstance(v, str):
            merged[k] = context.expand(v)

    validated = template.config_schema.model_validate(merged)
    return template.create(validated, context)


async def get_instance(session: AsyncSession, instance_id: str) -> CoreStorageInstance | None:
    return await session.get(CoreStorageInstance, instance_id)


async def list_instances(session: AsyncSession) -> list[CoreStorageInstance]:
    result = await session.execute(select(CoreStorageInstance))
    return list(result.scalars().all())


async def create_instance(
    session: AsyncSession,
    plugin_id: str,
    instance_name: str,
    raw_config: dict[str, Any],
    template: StorageTemplate,
) -> CoreStorageInstance:
    schema = template.config_schema.model_json_schema()
    template.config_schema.model_validate(raw_config)
    encrypted = encrypt_config(raw_config, schema)
    now = utcnow()
    instance = CoreStorageInstance(
        id=create_uuid(),
        plugin_id=plugin_id,
        instance_name=instance_name,
        config_json=json.dumps(encrypted),
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )
    session.add(instance)
    await session.flush()
    return instance


async def update_instance(
    session: AsyncSession,
    instance: CoreStorageInstance,
    template: StorageTemplate,
    instance_name: str | None = None,
    raw_config: dict[str, Any] | None = None,
    is_enabled: bool | None = None,
) -> CoreStorageInstance:
    if instance_name is not None:
        instance.instance_name = instance_name
    if raw_config is not None:
        schema = template.config_schema.model_json_schema()
        existing = json.loads(instance.config_json)
        # If client sent masked value, keep existing encrypted value
        merged_raw = {**existing}
        for k, v in raw_config.items():
            if _is_secret(schema, k) and v == _MASKED:
                merged_raw[k] = existing.get(k, "")
            else:
                merged_raw[k] = v
        template.config_schema.model_validate(decrypt_config(merged_raw, schema))
        encrypted = encrypt_config(decrypt_config(merged_raw, schema), schema)
        instance.config_json = json.dumps(encrypted)
    if is_enabled is not None:
        instance.is_enabled = is_enabled
    instance.updated_at = utcnow()
    await session.flush()
    return instance


async def get_user_config(
    session: AsyncSession, instance_id: str, user_id: str
) -> CoreStorageUserConfig | None:
    result = await session.execute(
        select(CoreStorageUserConfig).where(
            CoreStorageUserConfig.instance_id == instance_id,
            CoreStorageUserConfig.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_user_configs(session: AsyncSession, user_id: str) -> list[CoreStorageUserConfig]:
    result = await session.execute(
        select(CoreStorageUserConfig).where(CoreStorageUserConfig.user_id == user_id)
    )
    return list(result.scalars().all())


async def upsert_user_config(
    session: AsyncSession,
    instance: CoreStorageInstance,
    user_id: str,
    template: StorageTemplate,
    is_enabled: bool | None = None,
    raw_user_config: dict[str, Any] | None = None,
) -> CoreStorageUserConfig:
    user_cfg = await get_user_config(session, instance.id, user_id)
    schema = template.config_schema.model_json_schema()

    if user_cfg is None:
        user_cfg = CoreStorageUserConfig(
            id=create_uuid(),
            instance_id=instance.id,
            user_id=user_id,
            is_enabled=False,
            config_json="{}",
            updated_at=utcnow(),
        )
        session.add(user_cfg)

    if is_enabled is not None:
        user_cfg.is_enabled = is_enabled

    if raw_user_config is not None:
        existing = json.loads(user_cfg.config_json)
        user_editable_only: dict[str, Any] = {}
        for k, v in raw_user_config.items():
            if not _is_user_editable(schema, k):
                continue
            if _is_secret(schema, k) and v == _MASKED:
                user_editable_only[k] = existing.get(k, "")
            else:
                user_editable_only[k] = v
        encrypted = encrypt_config(user_editable_only, schema)
        user_cfg.config_json = json.dumps(encrypted)

    user_cfg.updated_at = utcnow()
    await session.flush()
    return user_cfg


async def resolve_backend_for_user(
    session: AsyncSession,
    instance_id: str,
    user_id: str,
    username: str,
    template_registry: StorageTemplateRegistry,
) -> StorageBackend | None:
    instance = await get_instance(session, instance_id)
    if instance is None or not instance.is_enabled:
        return None
    template = template_registry.get(instance.plugin_id)
    if template is None:
        L.warning("Instance %r references unknown template %r", instance_id, instance.plugin_id)
        return None
    user_cfg = await get_user_config(session, instance_id, user_id)
    if not is_instance_ready(instance, user_cfg, template):
        return None
    context = InstanceContext(user_id=user_id, username=username)
    return build_backend(instance, user_cfg, template, context)


async def list_ready_backends_for_user(
    session: AsyncSession,
    user_id: str,
    username: str,
    template_registry: StorageTemplateRegistry,
) -> list[tuple[CoreStorageInstance, StorageBackend]]:
    instances = await list_instances(session)
    user_cfgs = {uc.instance_id: uc for uc in await list_user_configs(session, user_id)}
    result: list[tuple[CoreStorageInstance, StorageBackend]] = []
    for inst in instances:
        if not inst.is_enabled:
            continue
        template = template_registry.get(inst.plugin_id)
        if template is None:
            continue
        user_cfg = user_cfgs.get(inst.id)
        if not is_instance_ready(inst, user_cfg, template):
            continue
        context = InstanceContext(user_id=user_id, username=username)
        result.append((inst, build_backend(inst, user_cfg, template, context)))
    return result


def instance_to_response(
    instance: CoreStorageInstance,
    template: StorageTemplate,
) -> dict[str, Any]:
    schema = template.config_schema.model_json_schema()
    stored = json.loads(instance.config_json)
    masked = mask_config(stored, schema)
    return {
        "id": instance.id,
        "plugin_id": instance.plugin_id,
        "instance_name": instance.instance_name,
        "config": masked,
        "is_enabled": instance.is_enabled,
        "created_at": instance.created_at.isoformat(),
        "updated_at": instance.updated_at.isoformat(),
    }


def user_config_to_response(
    instance: CoreStorageInstance,
    user_cfg: CoreStorageUserConfig | None,
    template: StorageTemplate,
) -> dict[str, Any]:
    schema = template.config_schema.model_json_schema()
    raw_user: dict[str, Any] = json.loads(user_cfg.config_json) if user_cfg else {}
    masked = mask_config(raw_user, schema)
    ready = is_instance_ready(instance, user_cfg, template) if user_cfg else False
    return {
        "instance_id": instance.id,
        "instance_name": instance.instance_name,
        "plugin_id": instance.plugin_id,
        "plugin_display_name": template.display_name,
        "is_enabled": user_cfg.is_enabled if user_cfg else False,
        "config": masked,
        "is_ready": ready,
    }


def backend_to_storage_meta(
    instance: CoreStorageInstance,
    backend: StorageBackend,
) -> ReadyBackendMeta:
    # id is the instance UUID — the value the client passes as ?backend=<id>.
    # backend.id is an internal plugin detail and must not be exposed here.
    return ReadyBackendMeta(
        id=instance.id,
        name=backend.name,
        plugin_id=instance.plugin_id,
    )
