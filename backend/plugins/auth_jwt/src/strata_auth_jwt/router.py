"""FastAPI router for the JWT auth plugin.

Endpoints
---------
POST /api/plugins/auth_jwt/register
    Create a new user account.

POST /api/plugins/auth_jwt/login
    Authenticate with username/password; returns access + refresh tokens.

POST /api/plugins/auth_jwt/refresh
    Exchange a valid refresh token for a new access token.

POST /api/plugins/auth_jwt/logout
    Revoke the current refresh token.

GET  /api/plugins/auth_jwt/me
    Return the currently authenticated user's profile.

All state lives in the shared Strata database via the
:data:`~strata.dependencies.db.AsyncSessionDep` dependency.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from strata.db.models import CoreUser
from strata.dependencies.db import AsyncSessionDep
from strata.schemas.auth import AuthUser
from strata_auth_jwt.config import settings
from strata_auth_jwt.models import RefreshToken, User
from strata_auth_jwt.schemas import (
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
from strata_auth_jwt.utils import (
    auth_user_from_token,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/plugins/auth_jwt/login")

plugin_router = APIRouter(prefix="/api/plugins/auth_jwt", tags=["auth"])


# ── Dependencies ──────────────────────────────────────────────────────────────


async def current_user_dep(
    token: Annotated[str, Depends(_oauth2_scheme)],
    session: AsyncSessionDep,
) -> AuthUser:
    """Validate the Bearer token and return the current :class:`~strata.plugins.protocols.AuthUser`.

    Args:
        token: JWT access token from the ``Authorization`` header.
        session: Async DB session (unused here — token is self-contained, but
            the dependency is kept so future blocklist checks have access).

    Returns:
        The authenticated :class:`~strata.plugins.protocols.AuthUser`.

    Raises:
        HTTPException: 401 if the token is invalid or expired.
    """
    return auth_user_from_token(token)


CurrentUserDep = Annotated[AuthUser, Depends(current_user_dep)]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def _get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── Routes ────────────────────────────────────────────────────────────────────


@plugin_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, session: AsyncSessionDep) -> UserResponse:
    """Register a new user account.

    Args:
        req: Registration payload with ``username`` and ``password``.
        session: Injected async DB session.

    Returns:
        The newly created user's public profile.

    Raises:
        HTTPException: 409 if *username* is already taken.
    """
    existing = await _get_user_by_username(session, req.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username {req.username!r} is already taken.",
        )

    # Create the platform identity row first; auth_jwt_users.id FKs to it.
    core_user = CoreUser()
    session.add(core_user)
    await session.flush()  # populate core_user.id

    user = User(
        id=core_user.id,  # share the same UUID
        username=req.username,
        hashed_password=hash_password(req.password),
    )
    session.add(user)
    await session.flush()
    return UserResponse(id=user.id, username=user.username, is_admin=user.is_admin)


@plugin_router.post("/login")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSessionDep,
) -> LoginResponse:
    """Authenticate a user and issue access + refresh tokens.

    Uses the standard OAuth2 password form (``application/x-www-form-urlencoded``
    with ``username`` and ``password`` fields) so it is compatible with the
    OpenAPI UI's ``Authorize`` button and any OAuth2-aware client.

    Args:
        form: OAuth2 password form.
        session: Injected async DB session.

    Returns:
        A :class:`~strata_auth_jwt.schemas.LoginResponse` with both tokens.

    Raises:
        HTTPException: 401 if the username does not exist or the password is wrong.
    """
    _auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await _get_user_by_username(session, form.username)
    if user is None:
        raise _auth_error
    if not verify_password(form.password, user.hashed_password):
        raise _auth_error

    # Issue tokens.
    access_token = create_access_token(user)
    raw_refresh, refresh_hash = generate_refresh_token()

    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=refresh_token_expiry(),
    )
    session.add(rt)

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@plugin_router.post("/refresh")
async def refresh(req: RefreshRequest, session: AsyncSessionDep) -> LoginResponse:
    """Exchange a valid refresh token for a new access token.

    The old refresh token is revoked and a fresh one is issued (token
    rotation), so each refresh token can only be used once.

    Args:
        req: Body containing the ``refresh_token`` string.
        session: Injected async DB session.

    Returns:
        A new :class:`~strata_auth_jwt.schemas.LoginResponse` with rotated tokens.

    Raises:
        HTTPException: 401 if the token is unknown, expired, or already revoked.
    """
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    hashed = hash_refresh_token(req.refresh_token)

    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashed,
        )
    )

    matched: RefreshToken | None = result.scalar_one_or_none()

    if matched is None or matched.is_expired():
        raise _invalid

    user = await _get_user_by_id(session, matched.user_id)
    if user is None:
        raise _invalid

    # Revoke old token.
    await session.delete(matched)

    # Issue new tokens (rotation).
    access_token = create_access_token(user)
    raw_refresh, refresh_hash = generate_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=refresh_token_expiry(),
    )
    session.add(new_rt)

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@plugin_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: RefreshRequest, session: AsyncSessionDep) -> None:
    """Revoke the provided refresh token.

    The access token remains valid until expiry (it is self-contained and
    short-lived).  Clients should discard it immediately after logout.

    Args:
        req: Body containing the ``refresh_token`` to revoke.
        session: Injected async DB session.
    """
    hashed = hash_refresh_token(req.refresh_token)

    await session.execute(
        delete(RefreshToken).where(
            RefreshToken.token_hash == hashed,
        )
    )


@plugin_router.get("/me")
async def me(current_user: CurrentUserDep) -> UserResponse:
    """Return the authenticated user's public profile.

    Args:
        current_user: Resolved from the ``Authorization: Bearer`` token.

    Returns:
        A :class:`~strata_auth_jwt.schemas.UserResponse` for the caller.
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        is_admin=current_user.is_admin,
    )
