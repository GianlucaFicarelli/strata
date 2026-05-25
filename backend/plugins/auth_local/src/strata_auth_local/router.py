"""FastAPI routes for the auth_local plugin.

Routes
------
POST /api/plugins/auth_local/login
    Verify credentials → create session → set HttpOnly cookie → return user.

POST /api/plugins/auth_local/logout
    Delete session → clear cookie → 204.

GET  /api/plugins/auth_local/invite/{token}
    Validate an invite token (not used, not expired) → 200.

POST /api/plugins/auth_local/invite/{token}/accept
    Create account using a valid invite → create session → 201 + user.

POST /api/admin/auth_local/invites
    Admin only — create an invite → return raw token once.
"""

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from strata.config import settings
from strata.db.models import CoreInvite, CoreUser
from strata.dependencies.auth import (
    CurrentUserDep,
    clear_session_cookie,
    session_cookie_helper,
)
from strata.dependencies.db import AsyncSessionDep
from strata.sessions.deps import SessionServiceDep
from strata.sessions.schemas import SessionData
from strata.utils import create_uuid, utcnow

from strata_auth_local.models import LocalUser
from strata_auth_local.schemas import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    LoginRequest,
    UserResponse,
)
from strata_auth_local.utils import hash_password, verify_password

L = logging.getLogger(__name__)

router = APIRouter(tags=["auth_local"])


# ── Helpers ────────────────────────────────────────────────────────────────────


def _token_hash(token: str) -> str:
    """Return the SHA-256 hex digest of *token*."""
    return hashlib.sha256(token.encode()).hexdigest()


async def _get_invite(db: AsyncSession, token: str) -> CoreInvite:
    """Fetch and validate an invite by raw token.

    Raises HTTP 404 if the invite does not exist, HTTP 410 if it has been
    used or has expired.
    """
    digest = _token_hash(token)
    result = await db.execute(select(CoreInvite).where(CoreInvite.token_hash == digest))
    invite = result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.is_used:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite already used")
    if invite.expires_at < utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has expired")

    return invite


def _build_session_data(core_user: CoreUser, local_user: LocalUser) -> SessionData:
    return SessionData(
        user_id=core_user.id,
        username=local_user.username,
        display_name=core_user.display_name,
        email=core_user.email,
        is_admin=core_user.is_admin,
    )


def _build_user_response(core_user: CoreUser, local_user: LocalUser) -> UserResponse:
    return UserResponse(
        id=core_user.id,
        username=local_user.username,
        display_name=core_user.display_name,
        email=core_user.email,
        is_admin=core_user.is_admin,
    )


# ── Login / logout ─────────────────────────────────────────────────────────────


@router.post("/api/plugins/auth_local/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSessionDep,
    session_service: SessionServiceDep,
) -> UserResponse:
    """Authenticate with username and password.

    On success sets the ``strata_session`` HttpOnly cookie and returns the
    user profile.  Returns HTTP 401 on invalid credentials (intentionally
    non-specific to prevent username enumeration).

    Args:
        body: ``{username, password}`` credentials.
        response: FastAPI response — used to attach the session cookie.
        db: Async DB session.
        session_service: Redis-backed session service.

    Returns:
        :class:`~strata_auth_local.schemas.UserResponse` for the authenticated user.

    Raises:
        HTTPException: 401 on invalid credentials.
    """
    result = await db.execute(
        select(LocalUser).where(LocalUser.username == body.username)
    )
    local_user = result.scalar_one_or_none()

    if local_user is None or not verify_password(body.password, local_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    core_result = await db.execute(
        select(CoreUser).where(CoreUser.id == local_user.id)
    )
    core_user = core_result.scalar_one()

    session_id = await session_service.create(_build_session_data(core_user, local_user))
    session_cookie_helper(response, session_id, session_service)
    L.info("User %r logged in", local_user.username)
    return _build_user_response(core_user, local_user)


@router.post("/api/plugins/auth_local/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session_service: SessionServiceDep,
    session_id: Annotated[
        str | None,
        Cookie(alias=settings.SESSION_COOKIE_NAME),
    ] = None,
) -> None:
    """Log out the current user.

    Deletes the session from Redis and clears the session cookie.  Safe to
    call when no session is active.

    Args:
        response: FastAPI response — used to clear the session cookie.
        session_service: Redis-backed session service.
        session_id: Value of the ``strata_session`` cookie; may be absent.
    """
    if session_id:
        await session_service.delete(session_id)
    clear_session_cookie(response)


# ── Invite acceptance ──────────────────────────────────────────────────────────


@router.get("/api/plugins/auth_local/invite/{token}")
async def validate_invite(token: str, db: AsyncSessionDep) -> dict[str, bool]:
    """Check whether an invite token is valid without consuming it.

    Returns ``{"valid": true}`` if the invite exists, is unused, and has not
    expired.  Raises HTTP 404 or 410 otherwise.

    Args:
        token: Raw invite token from the URL path.
        db: Async DB session.
    """
    await _get_invite(db, token)
    return {"valid": True}


@router.post(
    "/api/plugins/auth_local/invite/{token}/accept",
    status_code=status.HTTP_201_CREATED,
)
async def accept_invite(
    token: str,
    body: InviteAcceptRequest,
    response: Response,
    db: AsyncSessionDep,
    session_service: SessionServiceDep,
) -> UserResponse:
    """Create an account using a valid invite token.

    Creates a ``core_users`` row and an ``auth_local_users`` row, marks the
    invite as used, creates a session, and sets the ``strata_session`` cookie.

    Args:
        token: Raw invite token from the URL path.
        body: Account details: username, display_name, email, password.
        response: FastAPI response — used to attach the session cookie.
        db: Async DB session.
        session_service: Redis-backed session service.

    Returns:
        :class:`~strata_auth_local.schemas.UserResponse` for the new user.

    Raises:
        HTTPException: 404 / 410 if the invite is invalid or expired.
        HTTPException: 409 if the username or email is already taken.
    """
    invite = await _get_invite(db, token)

    now = utcnow()
    core_user = CoreUser(
        id=create_uuid(),
        display_name=body.display_name,
        email=body.email,
        is_admin=False,
        created_at=now,
        updated_at=now,
    )
    local_user = LocalUser(
        id=core_user.id,
        username=body.username,
        hashed_password=hash_password(body.password),
    )

    invite.used_by = core_user.id

    db.add(core_user)
    db.add(local_user)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        detail = str(exc.orig) if exc.orig else str(exc)
        if "username" in detail:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            ) from exc
        if "email" in detail:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account creation failed due to a conflict",
        ) from exc

    await db.refresh(core_user)
    await db.refresh(local_user)

    session_id = await session_service.create(_build_session_data(core_user, local_user))
    session_cookie_helper(response, session_id, session_service)
    L.info("New user %r registered via invite %r", local_user.username, invite.id)
    return _build_user_response(core_user, local_user)


# ── Admin: invite management ───────────────────────────────────────────────────


@router.post(
    "/api/admin/auth_local/invites",
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    body: InviteCreateRequest,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> InviteCreateResponse:
    """Create a single-use invite link (admin only).

    Generates a cryptographically random token, stores only its SHA-256 hash,
    and returns the raw token exactly once.  The caller is responsible for
    delivering the token out-of-band (e.g. via email).

    Args:
        body: ``{expires_in_hours}`` — invite lifetime.
        current_user: Authenticated admin user.
        db: Async DB session.

    Returns:
        :class:`~strata_auth_local.schemas.InviteCreateResponse` containing
        the one-time raw token.

    Raises:
        HTTPException: 403 if the caller is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    raw_token = secrets.token_urlsafe(32)
    now = utcnow()
    invite = CoreInvite(
        id=create_uuid(),
        token_hash=_token_hash(raw_token),
        created_by=current_user.id,
        used_by=None,
        expires_at=now + timedelta(hours=body.expires_in_hours),
        created_at=now,
    )
    db.add(invite)
    await db.commit()

    L.info(
        "Admin %r created invite %r (expires in %dh)",
        current_user.id,
        invite.id,
        body.expires_in_hours,
    )
    return InviteCreateResponse(
        invite_id=invite.id,
        token=raw_token,
        expires_in_hours=body.expires_in_hours,
    )
