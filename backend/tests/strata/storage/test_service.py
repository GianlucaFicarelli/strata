"""Unit + integration tests for strata.storage.service."""

import base64
import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from strata.crypto import encrypt_field
from strata.db.models import CoreStorageInstance, CoreStorageUserConfig, CoreUser
from strata.plugins.protocols import InstanceContext, StorageBackend
from strata.plugins.registry import StorageTemplateRegistry
from strata.schemas.common import StorageMeta
from strata.storage import service
from strata.utils import create_uuid, utcnow

# ── Minimal test schemas and templates ───────────────────────────────────────


class _SimpleConfig(BaseModel):
    root: str = Field(
        default="/data",
        json_schema_extra={"template": True},
    )


class _SecretConfig(BaseModel):
    host: str
    password: str = Field(json_schema_extra={"secret": True, "user_editable": True})
    username: str = Field(json_schema_extra={"user_editable": True})


class _FakeBackend:
    id: str = "fake:backend"
    name: str = "Fake"

    async def list(self, path: str) -> list:
        return []

    async def read(self, path: str):
        async def _g():
            yield b""

        return _g()

    async def write(self, path: str, stream: Any) -> None:
        pass

    async def delete(self, path: str) -> None:
        pass

    async def mkdir(self, path: str) -> None:
        pass

    async def move(self, src: str, dst: str) -> None:
        pass

    def describe(self):
        return StorageMeta(id=self.id, name=self.name)


class _SimpleTemplate:
    plugin_id = "simple"
    display_name = "Simple"
    description = "Test template"
    config_schema = _SimpleConfig
    created: list[tuple[Any, InstanceContext]]

    def __init__(self) -> None:
        self.created = []

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        self.created.append((config, context))
        return _FakeBackend()  # type: ignore[return-value]


class _SecretTemplate:
    plugin_id = "secret_tmpl"
    display_name = "Secret Template"
    description = "Template with secret user-editable fields"
    config_schema = _SecretConfig

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        return _FakeBackend()  # type: ignore[return-value]


# ── Field metadata helpers ────────────────────────────────────────────────────


def test_field_flags_template():
    schema = _SimpleConfig.model_json_schema()
    assert service._is_template_field(schema, "root")
    assert not service._is_secret(schema, "root")
    assert not service._is_user_editable(schema, "root")


def test_field_flags_secret_user_editable():
    schema = _SecretConfig.model_json_schema()
    assert service._is_secret(schema, "password")
    assert service._is_user_editable(schema, "password")
    assert service._is_user_editable(schema, "username")
    assert not service._is_secret(schema, "username")


def test_required_user_editable_fields():
    schema = _SecretConfig.model_json_schema()
    required = service._required_user_editable_fields(schema)
    assert required == {"password", "username"}


# ── Encryption helpers ────────────────────────────────────────────────────────


def _test_key() -> str:
    return base64.urlsafe_b64encode(b"A" * 32).decode()


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    schema = _SecretConfig.model_json_schema()
    raw = {"host": "server", "password": "hunter2", "username": "bob"}
    encrypted = service.encrypt_config(raw, schema)
    assert encrypted["password"] != "hunter2"
    assert encrypted["host"] == "server"  # not secret
    decrypted = service.decrypt_config(encrypted, schema)
    assert decrypted["password"] == "hunter2"
    assert decrypted["host"] == "server"


def test_mask_config():
    schema = _SecretConfig.model_json_schema()
    stored = {"host": "server", "password": "enc_blob", "username": "bob"}
    masked = service.mask_config(stored, schema)
    assert masked["password"] == "********"
    assert masked["host"] == "server"
    assert masked["username"] == "bob"


# ── Instance readiness ────────────────────────────────────────────────────────


def _make_instance(plugin_id: str = "simple", is_enabled: bool = True) -> CoreStorageInstance:
    return CoreStorageInstance(
        id=create_uuid(),
        plugin_id=plugin_id,
        instance_name="Test",
        config_json=json.dumps({"root": "/data/{username}"}),
        is_enabled=is_enabled,
        created_at=utcnow(),
        updated_at=utcnow(),
    )


def _make_user_config(
    instance_id: str,
    user_id: str,
    is_enabled: bool = True,
    cfg: dict | None = None,
) -> CoreStorageUserConfig:
    return CoreStorageUserConfig(
        id=create_uuid(),
        instance_id=instance_id,
        user_id=user_id,
        is_enabled=is_enabled,
        config_json=json.dumps(cfg or {}),
        updated_at=utcnow(),
    )


def test_is_instance_ready_no_user_config():
    inst = _make_instance()
    tmpl = _SimpleTemplate()
    assert not service.is_instance_ready(inst, None, tmpl)


def test_is_instance_ready_admin_disabled():
    inst = _make_instance(is_enabled=False)
    tmpl = _SimpleTemplate()
    user_cfg = _make_user_config(inst.id, "uid", is_enabled=True)
    assert not service.is_instance_ready(inst, user_cfg, tmpl)


def test_is_instance_ready_user_disabled():
    inst = _make_instance()
    tmpl = _SimpleTemplate()
    user_cfg = _make_user_config(inst.id, "uid", is_enabled=False)
    assert not service.is_instance_ready(inst, user_cfg, tmpl)


def test_is_instance_ready_no_required_user_fields():
    """Template with no user_editable fields is ready once user enables it."""
    inst = _make_instance()
    tmpl = _SimpleTemplate()
    user_cfg = _make_user_config(inst.id, "uid", is_enabled=True)
    assert service.is_instance_ready(inst, user_cfg, tmpl)


def test_is_instance_ready_missing_required_user_field():
    inst = _make_instance(plugin_id="secret_tmpl")
    tmpl = _SecretTemplate()
    # user_editable fields not filled
    user_cfg = _make_user_config(inst.id, "uid", is_enabled=True, cfg={})
    assert not service.is_instance_ready(inst, user_cfg, tmpl)


def test_is_instance_ready_all_required_user_fields_present():
    inst = _make_instance(plugin_id="secret_tmpl")
    tmpl = _SecretTemplate()
    user_cfg = _make_user_config(
        inst.id,
        "uid",
        is_enabled=True,
        cfg={"password": "enc_val", "username": "bob"},
    )
    assert service.is_instance_ready(inst, user_cfg, tmpl)


# ── build_backend ─────────────────────────────────────────────────────────────


def test_build_backend_template_expansion(monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    inst = _make_instance()
    inst.config_json = json.dumps({"root": "/home/{username}"})
    context = InstanceContext(user_id="uid-123", username="alice")
    service.build_backend(inst, None, tmpl, context)
    # The template was NOT called because user_cfg is None → is_instance_ready False
    # but build_backend itself doesn't check readiness — that's the caller's job.
    # Here we just verify the expansion happened inside create():
    assert len(tmpl.created) == 1
    config_passed, ctx_passed = tmpl.created[0]
    assert config_passed.root == "/home/alice"
    assert ctx_passed.username == "alice"


def test_build_backend_user_editable_overrides_admin(monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())

    key = _test_key()
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", key)

    class _UserOverrideTemplate:
        plugin_id = "ut"
        display_name = "UT"
        description = ""
        config_schema = _SecretConfig

        def __init__(self) -> None:
            self.received: list[Any] = []

        def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
            self.received.append(config)
            return _FakeBackend()  # type: ignore[return-value]

    tmpl = _UserOverrideTemplate()
    inst = CoreStorageInstance(
        id=create_uuid(),
        plugin_id="ut",
        instance_name="T",
        config_json=json.dumps({"host": "srv", "password": "", "username": "default"}),
        is_enabled=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    enc_pass = encrypt_field("mypass", key)
    user_cfg = _make_user_config(
        inst.id,
        "uid",
        is_enabled=True,
        cfg={"username": "alice", "password": enc_pass},
    )
    context = InstanceContext(user_id="uid", username="alice")
    service.build_backend(inst, user_cfg, tmpl, context)
    received_config = tmpl.received[0]
    assert received_config.username == "alice"
    assert received_config.password == "mypass"


# ── CRUD (integration with in-memory SQLite) ─────────────────────────────────


async def test_create_and_get_instance(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    inst = await service.create_instance(
        db_session,
        plugin_id="simple",
        instance_name="My Files",
        raw_config={"root": "/data/{username}"},
        template=tmpl,
    )
    assert inst.id
    assert inst.plugin_id == "simple"
    assert inst.instance_name == "My Files"

    fetched = await service.get_instance(db_session, inst.id)
    assert fetched is not None
    assert fetched.instance_name == "My Files"


async def test_list_instances(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    await service.create_instance(db_session, "simple", "A", {"root": "/a"}, tmpl)
    await service.create_instance(db_session, "simple", "B", {"root": "/b"}, tmpl)
    instances = await service.list_instances(db_session)
    assert len(instances) == 2


async def test_upsert_user_config(db_session: AsyncSession, core_user: CoreUser, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    inst = await service.create_instance(db_session, "simple", "My Files", {"root": "/data"}, tmpl)

    # First call creates the row
    user_cfg = await service.upsert_user_config(
        db_session, inst, core_user.id, tmpl, is_enabled=True
    )
    assert user_cfg.is_enabled is True

    # Second call updates it
    user_cfg2 = await service.upsert_user_config(
        db_session, inst, core_user.id, tmpl, is_enabled=False
    )
    assert user_cfg2.is_enabled is False
    assert user_cfg2.id == user_cfg.id  # same row


async def test_resolve_backend_not_ready(
    db_session: AsyncSession, core_user: CoreUser, monkeypatch
):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    inst = await service.create_instance(db_session, "simple", "Files", {"root": "/data"}, tmpl)
    reg = StorageTemplateRegistry()
    reg.add(tmpl)

    # No user config → not ready
    result = await service.resolve_backend_for_user(db_session, inst.id, core_user.id, "alice", reg)
    assert result is None


async def test_resolve_backend_ready(db_session: AsyncSession, core_user: CoreUser, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    inst = await service.create_instance(db_session, "simple", "Files", {"root": "/data"}, tmpl)
    await service.upsert_user_config(db_session, inst, core_user.id, tmpl, is_enabled=True)

    reg = StorageTemplateRegistry()
    reg.add(tmpl)
    backend = await service.resolve_backend_for_user(
        db_session, inst.id, core_user.id, "alice", reg
    )
    assert backend is not None


async def test_update_instance(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _SimpleTemplate()
    inst = await service.create_instance(db_session, "simple", "Old Name", {"root": "/old"}, tmpl)
    updated = await service.update_instance(
        db_session, inst, tmpl, instance_name="New Name", is_enabled=False
    )
    assert updated.instance_name == "New Name"
    assert updated.is_enabled is False
