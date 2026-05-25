"""Integration tests for /api/admin/storage/* endpoints."""

import base64
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from strata.db.models import CoreUser
from strata.dependencies.auth import _require_current_user
from strata.dependencies.db import db_session_dep
from strata.dependencies.registry import storage_template_registry_dep
from strata.main import app
from strata.plugins.protocols import InstanceContext, StorageBackend
from strata.plugins.registry import StorageTemplateRegistry
from tests.conftest import make_admin_auth_user, make_auth_user


def _test_key() -> str:
    return base64.urlsafe_b64encode(b"B" * 32).decode()


class _AdminTestConfig(BaseModel):
    root: str = Field(default="/srv", json_schema_extra={"template": True})
    token: str = Field(default="", json_schema_extra={"secret": True})


class _AdminTestTemplate:
    plugin_id = "admin_test"
    display_name = "Admin Test"
    description = "Template for admin API tests"
    config_schema = _AdminTestConfig

    def create(self, config: BaseModel, context: InstanceContext) -> StorageBackend:
        raise NotImplementedError


@pytest.fixture
def template_registry() -> StorageTemplateRegistry:
    reg = StorageTemplateRegistry()
    reg.add(_AdminTestTemplate())
    return reg


def _setup_overrides(core_user, db_session, template_registry, monkeypatch, *, is_admin):
    monkeypatch.setattr("strata.storage.service.settings.ENCRYPTION_KEY", _test_key())
    user = (
        make_admin_auth_user(core_user) if is_admin else make_auth_user(core_user, is_admin=False)
    )
    app.dependency_overrides[_require_current_user] = lambda: user
    app.dependency_overrides[storage_template_registry_dep] = lambda: template_registry
    app.dependency_overrides[db_session_dep] = lambda: db_session


def _teardown_overrides():
    app.dependency_overrides.pop(_require_current_user, None)
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)


@pytest_asyncio.fixture
async def http_admin(
    core_user: CoreUser,
    db_session: AsyncSession,
    template_registry: StorageTemplateRegistry,
    monkeypatch,
) -> AsyncGenerator[AsyncClient]:
    _setup_overrides(core_user, db_session, template_registry, monkeypatch, is_admin=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    _teardown_overrides()


@pytest_asyncio.fixture
async def http_non_admin(
    core_user: CoreUser,
    db_session: AsyncSession,
    template_registry: StorageTemplateRegistry,
    monkeypatch,
) -> AsyncGenerator[AsyncClient]:
    _setup_overrides(core_user, db_session, template_registry, monkeypatch, is_admin=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    _teardown_overrides()


# ── Template listing ──────────────────────────────────────────────────────────


async def test_list_templates(http_admin: AsyncClient):
    resp = await http_admin.get("/api/admin/storage/templates")
    assert resp.status_code == 200
    assert any(t["plugin_id"] == "admin_test" for t in resp.json())


async def test_list_templates_forbidden_for_non_admin(http_non_admin: AsyncClient):
    resp = await http_non_admin.get("/api/admin/storage/templates")
    assert resp.status_code == 403


async def test_template_schema_contains_field_flags(http_admin: AsyncClient):
    resp = await http_admin.get("/api/admin/storage/templates")
    tmpl = next(t for t in resp.json() if t["plugin_id"] == "admin_test")
    props = tmpl["config_schema"]["properties"]
    assert props["token"].get("secret") is True
    assert props["root"].get("template") is True


# ── Instance CRUD ─────────────────────────────────────────────────────────────


async def test_create_instance(http_admin: AsyncClient):
    resp = await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "My Storage",
            "config": {"root": "/data/{username}", "token": "secret123"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["instance_name"] == "My Storage"
    assert data["plugin_id"] == "admin_test"
    assert data["config"]["token"] == "********"  # secret → masked
    assert data["config"]["root"] == "/data/{username}"  # template, not secret


async def test_create_instance_unknown_template(http_admin: AsyncClient):
    resp = await http_admin.post(
        "/api/admin/storage/instances",
        json={"plugin_id": "nonexistent", "instance_name": "X", "config": {}},
    )
    assert resp.status_code == 400


async def test_create_forbidden_for_non_admin(http_non_admin: AsyncClient):
    resp = await http_non_admin.post(
        "/api/admin/storage/instances",
        json={"plugin_id": "admin_test", "instance_name": "X", "config": {}},
    )
    assert resp.status_code == 403


async def test_get_instance(http_admin: AsyncClient):
    cr = await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "Fetch Me",
            "config": {"root": "/x", "token": "tok"},
        },
    )
    inst_id = cr.json()["id"]
    resp = await http_admin.get(f"/api/admin/storage/instances/{inst_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == inst_id


async def test_get_instance_not_found(http_admin: AsyncClient):
    resp = await http_admin.get("/api/admin/storage/instances/does-not-exist")
    assert resp.status_code == 404


async def test_update_instance(http_admin: AsyncClient):
    cr = await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "Old",
            "config": {"root": "/old", "token": "tok"},
        },
    )
    inst_id = cr.json()["id"]
    resp = await http_admin.put(
        f"/api/admin/storage/instances/{inst_id}",
        json={"instance_name": "New", "is_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["instance_name"] == "New"
    assert resp.json()["is_enabled"] is False


async def test_update_secret_with_masked_preserves_value(http_admin: AsyncClient):
    """Sending '********' for a secret field on update keeps the original."""
    cr = await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "S",
            "config": {"root": "/r", "token": "real_tok"},
        },
    )
    inst_id = cr.json()["id"]
    resp = await http_admin.put(
        f"/api/admin/storage/instances/{inst_id}",
        json={"instance_name": "S2", "config": {"root": "/r2", "token": "********"}},
    )
    assert resp.status_code == 200
    # Token is still masked (not lost, not empty)
    assert resp.json()["config"]["token"] == "********"


async def test_delete_instance(http_admin: AsyncClient):
    cr = await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "Delete Me",
            "config": {"root": "/tmp", "token": "x"},
        },
    )
    inst_id = cr.json()["id"]
    dr = await http_admin.delete(f"/api/admin/storage/instances/{inst_id}")
    assert dr.status_code == 204
    gr = await http_admin.get(f"/api/admin/storage/instances/{inst_id}")
    assert gr.status_code == 404


async def test_delete_not_found(http_admin: AsyncClient):
    resp = await http_admin.delete("/api/admin/storage/instances/no-such-id")
    assert resp.status_code == 404


async def test_list_instances(http_admin: AsyncClient):
    await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "A",
            "config": {"root": "/a", "token": ""},
        },
    )
    await http_admin.post(
        "/api/admin/storage/instances",
        json={
            "plugin_id": "admin_test",
            "instance_name": "B",
            "config": {"root": "/b", "token": ""},
        },
    )
    resp = await http_admin.get("/api/admin/storage/instances")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
