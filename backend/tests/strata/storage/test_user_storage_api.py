"""Integration tests for /api/storage/instances/* (user self-service)."""

import base64

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from strata.db.models import CoreUser
from strata.dependencies.auth import require_current_user_dep
from strata.dependencies.db import db_session_dep
from strata.dependencies.registry import storage_template_registry_dep
from strata.main import app
from strata.plugins.protocols import InstanceContext, StorageBackend
from strata.plugins.registry import StorageTemplateRegistry
from strata.storage import service

from tests.conftest import make_auth_user


def _test_key() -> str:
    return base64.urlsafe_b64encode(b"C" * 32).decode()


class _UserTestConfig(BaseModel):
    host: str = Field(default="fileserver")
    username: str = Field(json_schema_extra={"user_editable": True})
    password: str = Field(json_schema_extra={"secret": True, "user_editable": True})


class _UserTestTemplate:
    plugin_id = "user_test"
    display_name = "User Test"
    description = "Template for user API tests"
    config_schema = _UserTestConfig

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        raise NotImplementedError


class _NoUserFieldsConfig(BaseModel):
    root: str = Field(default="/shared", json_schema_extra={"template": True})


class _NoUserFieldsTemplate:
    plugin_id = "no_user_fields"
    display_name = "No User Fields"
    description = "Template with no user_editable fields"
    config_schema = _NoUserFieldsConfig

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        raise NotImplementedError


@pytest.fixture
def template_registry() -> StorageTemplateRegistry:
    reg = StorageTemplateRegistry()
    reg.add(_UserTestTemplate())
    reg.add(_NoUserFieldsTemplate())
    return reg


@pytest_asyncio.fixture
async def http_user(
    core_user: CoreUser,
    db_session: AsyncSession,
    template_registry: StorageTemplateRegistry,
    monkeypatch,
) -> AsyncClient:
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    user = make_auth_user(core_user, username="alice")
    app.dependency_overrides[require_current_user_dep] = lambda: user
    app.dependency_overrides[storage_template_registry_dep] = lambda: template_registry
    app.dependency_overrides[db_session_dep] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(require_current_user_dep, None)
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)


@pytest_asyncio.fixture
async def instance_with_user_fields(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _UserTestTemplate()
    return await service.create_instance(
        db_session, "user_test", "SMB Share", {"host": "srv", "username": "", "password": ""}, tmpl
    )


@pytest_asyncio.fixture
async def instance_no_user_fields(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    tmpl = _NoUserFieldsTemplate()
    return await service.create_instance(
        db_session, "no_user_fields", "Shared Docs", {"root": "/docs/{username}"}, tmpl
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_list_instances_returns_all_admin_enabled(
    http_user: AsyncClient,
    instance_with_user_fields,
    instance_no_user_fields,
):
    resp = await http_user.get("/api/storage/instances")
    assert resp.status_code == 200
    ids = {i["instance_id"] for i in resp.json()}
    assert instance_with_user_fields.id in ids
    assert instance_no_user_fields.id in ids


async def test_list_instances_excludes_admin_disabled(
    http_user: AsyncClient,
    db_session: AsyncSession,
    instance_with_user_fields,
    monkeypatch,
):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    instance_with_user_fields.is_enabled = False
    await db_session.flush()
    resp = await http_user.get("/api/storage/instances")
    ids = {i["instance_id"] for i in resp.json()}
    assert instance_with_user_fields.id not in ids


async def test_get_user_instance_config_not_configured(
    http_user: AsyncClient,
    instance_with_user_fields,
):
    resp = await http_user.get(f"/api/storage/instances/{instance_with_user_fields.id}/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_enabled"] is False
    assert data["is_ready"] is False


async def test_enable_instance_no_user_fields_becomes_ready(
    http_user: AsyncClient,
    instance_no_user_fields,
):
    """An instance with no user_editable fields is immediately ready when enabled."""
    resp = await http_user.patch(
        f"/api/storage/instances/{instance_no_user_fields.id}/me",
        json={"is_enabled": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_enabled"] is True
    assert data["is_ready"] is True


async def test_enable_instance_with_missing_required_fields_not_ready(
    http_user: AsyncClient,
    instance_with_user_fields,
):
    resp = await http_user.patch(
        f"/api/storage/instances/{instance_with_user_fields.id}/me",
        json={"is_enabled": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_enabled"] is True
    assert data["is_ready"] is False


async def test_fill_user_fields_makes_ready(
    http_user: AsyncClient,
    instance_with_user_fields,
):
    resp = await http_user.patch(
        f"/api/storage/instances/{instance_with_user_fields.id}/me",
        json={
            "is_enabled": True,
            "config": {"username": "alice", "password": "secret"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_ready"] is True
    assert data["config"]["password"] == "********"  # masked in response


async def test_secret_field_masked_roundtrip(
    http_user: AsyncClient,
    instance_with_user_fields,
):
    """Sending '********' for a secret preserves the existing encrypted value."""
    # First set a real password
    await http_user.patch(
        f"/api/storage/instances/{instance_with_user_fields.id}/me",
        json={"is_enabled": True, "config": {"username": "alice", "password": "real_pass"}},
    )
    # Then update only username, sending masked for password
    resp = await http_user.patch(
        f"/api/storage/instances/{instance_with_user_fields.id}/me",
        json={"config": {"username": "alice2", "password": "********"}},
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["password"] == "********"
    assert resp.json()["config"]["username"] == "alice2"


async def test_patch_not_found(http_user: AsyncClient):
    resp = await http_user.patch(
        "/api/storage/instances/no-such-id/me",
        json={"is_enabled": True},
    )
    assert resp.status_code == 404


async def test_get_not_found(http_user: AsyncClient):
    resp = await http_user.get("/api/storage/instances/no-such-id/me")
    assert resp.status_code == 404


async def test_non_user_editable_fields_ignored(
    http_user: AsyncClient,
    instance_with_user_fields,
):
    """Fields not marked user_editable in the schema must be silently ignored."""
    resp = await http_user.patch(
        f"/api/storage/instances/{instance_with_user_fields.id}/me",
        json={"config": {"host": "evil_override", "username": "alice", "password": "p"}},
    )
    assert resp.status_code == 200
    # host is admin-only; it must NOT appear in the user config response
    assert "host" not in resp.json()["config"]
