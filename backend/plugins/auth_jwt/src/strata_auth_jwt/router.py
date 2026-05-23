"""FastAPI router for the JWT auth plugin.

Endpoints
---------
POST /api/plugins/auth_jwt/register
    Create a new user account.

POST /api/plugins/auth_jwt/login
    Authenticate with username/password; returns the access token in the
    response body and sets the refresh token as an HttpOnly cookie.

POST /api/plugins/auth_jwt/refresh
    Issue a new access token by reading the refresh token from the HttpOnly
    cookie.  Rotates the refresh token: the old cookie is cleared and a new
    one is set.  Requires no request body.

POST /api/plugins/auth_jwt/logout
    Revoke the refresh token read from the HttpOnly cookie and clear it.
    Requires no request body.

GET  /api/plugins/auth_jwt/me
    Return the currently authenticated user's profile.

All state lives in the shared Strata database via the
:data:`~strata.dependencies.db.AsyncSessionDep` dependency.

Cookie design
-------------
The refresh token is stored in an HttpOnly cookie named
``strata_refresh_token``.  HttpOnly means JavaScript cannot read it, which
closes the XSS exfiltration vector that affects localStorage.

Cookie attributes set in production (STRATA_JWT_COOKIE_SECURE=true):
    HttpOnly      — not readable by JS
    Secure        — HTTPS only
    SameSite=Strict — only sent to same-origin requests (CSRF protection)
    Path=/api/plugins/auth_jwt — scoped to auth endpoints only, so the
        cookie is not sent on every API request.

For local HTTP development set STRATA_JWT_COOKIE_SECURE=false.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from strata.db.models import CoreUser
from strata.dependencies.db import AsyncSessionDep
from strata.schemas.auth import AuthUser
from strata_auth_jwt.config import settings
from strata_auth_jwt.models import RefreshToken, User
from strata_auth_jwt.schemas import LoginResponse, RegisterRequest, UserResponse
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

# Name of the HttpOnly cookie that carries the refresh token.
_REFRESH_COOKIE = "strata_refresh_token"
# Path scope: the cookie is only sent to endpoints under this prefix.
_COOKIE_PATH = "/api/plugins/auth_jwt"


# ── Cookie helpers ────────────────────────────────────────────────────────────


def _set_refresh_cookie(response: Response, raw_refresh: str) -> None:
    """Attach the refresh token as an HttpOnly cookie to *response*."""
    max_age = settings.JWT_REFRESH_EXPIRE_DAYS * 86_400
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=raw_refresh,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        path=_COOKIE_PATH,
        max_age=max_age,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Delete the refresh-token cookie by expiring it immediately."""
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        path=_COOKIE_PATH,
    )


# ── Dependencies ──────────────────────────────────────────────────────────────


async def current_user_dep(
    token: Annotated[str, Depends(_oauth2_scheme)],
    session: AsyncSessionDep,
) -> AuthUser:
    """Validate the Bearer token and return the current AuthUser.

    Args:
        token: JWT access token from the ``Authorization`` header.
        session: Async DB session (kept for future blocklist support).

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
        id=core_user.id,
        username=req.username,
        hashed_password=hash_password(req.password),
    )
    session.add(user)
    await session.flush()
    return UserResponse(id=user.id, username=user.username, is_admin=user.is_admin)


@plugin_router.post("/login")
async def login(
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSessionDep,
) -> LoginResponse:
    """Authenticate a user and issue tokens.

    The access token is returned in the response body.  The refresh token is
    delivered as an HttpOnly cookie (``strata_refresh_token``) so that
    JavaScript cannot read it.

    Args:
        response: FastAPI response object used to set the cookie.
        form: OAuth2 password form (compatible with the OpenAPI /docs UI).
        session: Injected async DB session.

    Returns:
        A :class:`~strata_auth_jwt.schemas.LoginResponse` with the access token.

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

    access_token = create_access_token(user)
    raw_refresh, refresh_hash = generate_refresh_token()

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_token_expiry(),
        )
    )

    _set_refresh_cookie(response, raw_refresh)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@plugin_router.post("/refresh")
async def refresh(
    response: Response,
    session: AsyncSessionDep,
    cookie_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
) -> LoginResponse:
    """Exchange a valid refresh token for a new access token.

    Reads the refresh token exclusively from the HttpOnly cookie
    ``strata_refresh_token``.  The old token is revoked and a fresh cookie
    is set (token rotation).  No request body is accepted or needed.

    Args:
        response: Used to set the rotated refresh-token cookie.
        session: Injected async DB session.
        cookie_token: Refresh token from the HttpOnly cookie.

    Returns:
        A new :class:`~strata_auth_jwt.schemas.LoginResponse`.

    Raises:
        HTTPException: 401 if the cookie is absent, unknown, expired, or
            already revoked.
    """
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not cookie_token:
        raise _invalid

    hashed = hash_refresh_token(cookie_token)
    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == hashed))
    matched: RefreshToken | None = result.scalar_one_or_none()

    if matched is None or matched.is_expired():
        raise _invalid

    user = await _get_user_by_id(session, matched.user_id)
    if user is None:
        raise _invalid

    # Revoke the consumed token.
    await session.delete(matched)

    # Issue a fresh token pair.
    access_token = create_access_token(user)
    raw_refresh, refresh_hash = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_token_expiry(),
        )
    )

    _set_refresh_cookie(response, raw_refresh)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@plugin_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: AsyncSessionDep,
    cookie_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
) -> None:
    """Revoke the refresh token and clear the cookie.

    Reads the token exclusively from the HttpOnly cookie.  The access token
    remains valid until its natural expiry — it is self-contained and
    short-lived.  No request body is accepted or needed.

    Args:
        response: Used to clear the refresh-token cookie.
        session: Injected async DB session.
        cookie_token: Refresh token from the HttpOnly cookie.
    """
    if cookie_token:
        hashed = hash_refresh_token(cookie_token)
        await session.execute(delete(RefreshToken).where(RefreshToken.token_hash == hashed))
    _clear_refresh_cookie(response)


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
