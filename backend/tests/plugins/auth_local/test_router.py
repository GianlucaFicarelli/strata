"""Integration tests for auth_local login/logout/invite routes."""

import hashlib
import secrets
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.db.models import CoreInvite, CoreUser
from strata.dependencies.db import db_session_dep
from strata.dependencies.auth import _require_current_user
from strata.main import app
from strata.sessions.deps import SessionServiceDep
from strata.sessions.service import SessionService
from strata.utils import create_uuid, utcnow
from strata_auth_local.models import LocalUser
from strata_auth_local.utils import hash_password
from tests.conftest import make_admin_auth_user, make_auth_user, make_mock_session_service


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> tuple[CoreUser, LocalUser]:
    """A persisted alice user with password 'password123'."""
    now = utcnow()
    core = CoreUser(
        id=create_uuid(),
        display_name="Alice",
        email="alice@example.com",
        is_admin=False,
        created_at=now,
        updated_at=now,
    )
    local = LocalUser(
        id=core.id,
        username="alice",
        hashed_password=hash_password("password123"),
    )
    db_session.add(core)
    db_session.add(local)
    await db_session.flush()
    return core, local


@pytest_asyncio.fixture
async def valid_invite(
    db_session: AsyncSession,
    admin_user: CoreUser,
) -> tuple[CoreInvite, str]:
    """A valid unused invite created by admin_user. Returns (invite, raw_token)."""
    raw_token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    now = utcnow()
    invite = CoreInvite(
        id=create_uuid(),
        token_hash=digest,
        created_by=admin_user.id,
        used_by=None,
        expires_at=now + timedelta(hours=48),
        created_at=now,
    )
    db_session.add(invite)
    await db_session.flush()
    return invite, raw_token


@pytest_asyncio.fixture
async def expired_invite(
    db_session: AsyncSession,
    admin_user: CoreUser,
) -> tuple[CoreInvite, str]:
    """An expired invite."""
    raw_token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    now = utcnow()
    invite = CoreInvite(
        id=create_uuid(),
        token_hash=digest,
        created_by=admin_user.id,
        used_by=None,
        expires_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=49),
    )
    db_session.add(invite)
    await db_session.flush()
    return invite, raw_token


@pytest.fixture
def mock_session_svc() -> SessionService:
    return make_mock_session_service()


@pytest.fixture
def override_deps(db_session: AsyncSession, mock_session_svc: SessionService):
    """Override DB and session deps for all auth_local route tests."""
    from strata.sessions import deps as sdeps

    app.dependency_overrides[db_session_dep] = lambda: db_session
    app.dependency_overrides[sdeps._session_service_dep] = lambda: mock_session_svc
    yield
    app.dependency_overrides.pop(db_session_dep, None)
    app.dependency_overrides.pop(sdeps._session_service_dep, None)


@pytest_asyncio.fixture
async def http(override_deps) -> AsyncIterator[AsyncClient]:
    from collections.abc import AsyncIterator
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Login ─────────────────────────────────────────────────────────────────────


async def test_login_success(
    http: AsyncClient,
    alice: tuple[CoreUser, LocalUser],
    mock_session_svc: SessionService,
):
    resp = await http.post(
        "/api/plugins/auth_local/login",
        json={"username": "alice", "password": "password123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["display_name"] == "Alice"
    # Cookie should be set
    assert "strata_session" in resp.cookies
    # Session was created
    mock_session_svc.create.assert_called_once()


async def test_login_wrong_password(http: AsyncClient, alice):
    resp = await http.post(
        "/api/plugins/auth_local/login",
        json={"username": "alice", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(http: AsyncClient):
    resp = await http.post(
        "/api/plugins/auth_local/login",
        json={"username": "ghost", "password": "whatever"},
    )
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


async def test_logout_clears_cookie(
    http: AsyncClient,
    mock_session_svc: SessionService,
):
    # Set a fake session cookie
    http.cookies.set("strata_session", "fake-session-id")
    resp = await http.post("/api/plugins/auth_local/logout")
    assert resp.status_code == 204
    mock_session_svc.delete.assert_called_once_with("fake-session-id")


async def test_logout_without_cookie_is_safe(http: AsyncClient, mock_session_svc: SessionService):
    resp = await http.post("/api/plugins/auth_local/logout")
    assert resp.status_code == 204
    mock_session_svc.delete.assert_not_called()


# ── Invite validation ─────────────────────────────────────────────────────────


async def test_validate_invite_valid(
    http: AsyncClient,
    valid_invite: tuple[CoreInvite, str],
):
    _, token = valid_invite
    resp = await http.get(f"/api/plugins/auth_local/invite/{token}")
    assert resp.status_code == 200
    assert resp.json() == {"valid": True}


async def test_validate_invite_not_found(http: AsyncClient):
    resp = await http.get("/api/plugins/auth_local/invite/nonexistenttoken")
    assert resp.status_code == 404


async def test_validate_invite_expired(
    http: AsyncClient,
    expired_invite: tuple[CoreInvite, str],
):
    _, token = expired_invite
    resp = await http.get(f"/api/plugins/auth_local/invite/{token}")
    assert resp.status_code == 410


# ── Accept invite ─────────────────────────────────────────────────────────────


async def test_accept_invite_creates_user(
    http: AsyncClient,
    db_session: AsyncSession,
    valid_invite: tuple[CoreInvite, str],
    mock_session_svc: SessionService,
):
    invite, token = valid_invite
    resp = await http.post(
        f"/api/plugins/auth_local/invite/{token}/accept",
        json={
            "username": "bob",
            "display_name": "Bob",
            "email": "bob@example.com",
            "password": "securepass1",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "bob"
    assert body["display_name"] == "Bob"
    assert "strata_session" in resp.cookies
    mock_session_svc.create.assert_called_once()

    # Invite should be marked as used
    await db_session.refresh(invite)
    assert invite.is_used


async def test_accept_invite_duplicate_username(
    http: AsyncClient,
    valid_invite: tuple[CoreInvite, str],
    alice: tuple[CoreUser, LocalUser],
):
    _, token = valid_invite
    resp = await http.post(
        f"/api/plugins/auth_local/invite/{token}/accept",
        json={
            "username": "alice",  # already taken
            "display_name": "Alice 2",
            "password": "securepass1",
        },
    )
    assert resp.status_code == 409


async def test_accept_expired_invite_fails(
    http: AsyncClient,
    expired_invite: tuple[CoreInvite, str],
):
    _, token = expired_invite
    resp = await http.post(
        f"/api/plugins/auth_local/invite/{token}/accept",
        json={"username": "new", "display_name": "New", "password": "securepass1"},
    )
    assert resp.status_code == 410


# ── Admin: create invite ──────────────────────────────────────────────────────


async def test_create_invite_as_admin(
    http: AsyncClient,
    db_session: AsyncSession,
    admin_user: CoreUser,
):
    admin_auth = make_admin_auth_user(admin_user)
    app.dependency_overrides[_require_current_user] = lambda: admin_auth
    try:
        resp = await http.post(
            "/api/admin/auth_local/invites",
            json={"expires_in_hours": 24},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "token" in body
        assert "invite_id" in body
        assert body["expires_in_hours"] == 24
    finally:
        app.dependency_overrides.pop(_require_current_user, None)


async def test_create_invite_as_non_admin_returns_403(
    http: AsyncClient,
    core_user: CoreUser,
):
    user = make_auth_user(core_user, username="alice", is_admin=False)
    app.dependency_overrides[_require_current_user] = lambda: user
    try:
        resp = await http.post(
            "/api/admin/auth_local/invites",
            json={"expires_in_hours": 24},
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(_require_current_user, None)


async def test_create_invite_unauthenticated(http: AsyncClient):
    """No session → 401 from CurrentUserDep."""
    resp = await http.post(
        "/api/admin/auth_local/invites",
        json={"expires_in_hours": 24},
    )
    assert resp.status_code == 401
