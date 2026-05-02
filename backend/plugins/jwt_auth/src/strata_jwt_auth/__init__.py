"""JWT-based password authentication plugin for Strata.

Contributes:

- :class:`~strata.plugins.protocols.AuthProvider`: validates username/password
  credentials against a local SQLite user store and returns an
  :class:`~strata.plugins.protocols.AuthUser`.
- :class:`~strata.plugins.protocols.RouteProvider`: exposes
  ``POST /api/plugins/jwt_auth/register``,
  ``POST /api/plugins/jwt_auth/login``, and
  ``POST /api/plugins/jwt_auth/logout`` endpoints.

Entry point::

    [project.entry-points."strata.plugins"]
    jwt_auth = "strata_jwt_auth:plugin"

Configuration:
    STRATA_JWT_SECRET: Secret key used to sign JWT tokens.  **Must** be set
        to a long random string in production.
    STRATA_JWT_EXPIRE_MINUTES: Access token lifetime in minutes (default 15).
    STRATA_AUTH_DB_URL: SQLAlchemy async database URL
        (default ``"sqlite+aiosqlite:///~/.strata/auth.db"``).

Security note:
    Passwords are hashed with Argon2 via passlib.  JWTs are signed with
    HS256.  This is a stub — the SQLAlchemy models, Alembic migrations, and
    refresh token logic are marked with ``TODO`` comments.
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from strata.plugins.base import BackendPlugin
from strata.plugins.protocols import AuthUser
from strata.plugins.registry import PluginRegistry

_JWT_SECRET: str = os.environ.get("STRATA_JWT_SECRET", "change-me-in-production")
_JWT_ALGORITHM: str = "HS256"
_JWT_EXPIRE_MINUTES: int = int(os.environ.get("STRATA_JWT_EXPIRE_MINUTES", "15"))
_AUTH_DB_URL: str = os.environ.get(
    "STRATA_AUTH_DB_URL",
    f"sqlite+aiosqlite:///{Path('~').expanduser()}/.strata/auth.db",
)

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/plugins/jwt_auth/login")

# ── Pydantic schemas ──────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Request body for user registration.

    Attributes:
        username: Desired username or email address.
        password: Plain-text password (hashed before storage).
    """

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response body for a successful login.

    Attributes:
        access_token: Signed JWT access token.
        token_type: Always ``"bearer"``.
    """

    access_token: str
    token_type: str = "bearer"


# ── Token helpers ─────────────────────────────────────────────────────────────


def _create_access_token(user_id: str, username: str, is_admin: bool) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: Opaque user identifier (database primary key).
        username: Username or email to embed in the token.
        is_admin: Whether the user has admin privileges.

    Returns:
        A signed JWT string.
    """
    expire = datetime.now(UTC) + timedelta(minutes=_JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: Signed JWT string.

    Returns:
        The decoded payload dict.

    Raises:
        HTTPException: 401 if the token is invalid or expired.
    """
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── API routes ────────────────────────────────────────────────────────────────

_router = APIRouter(prefix="/api/plugins/jwt_auth", tags=["auth"])


@_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest) -> dict[str, str]:
    """Register a new user account.

    Args:
        req: Registration request with ``username`` and ``password``.

    Returns:
        A dict with a ``"status": "created"`` key.

    Raises:
        HTTPException: 409 if *username* is already taken.

    Todo:
        - Check for duplicate username in the database.
        - Hash the password: ``_pwd_context.hash(req.password)``.
        - Insert a new ``User`` row via SQLAlchemy.
    """
    return {"status": "created"}  # TODO: implement with SQLAlchemy


@_router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """Authenticate a user and return a JWT access token.

    Args:
        form: OAuth2 password form with ``username`` and ``password`` fields.

    Returns:
        A :class:`TokenResponse` containing the signed access token.

    Raises:
        HTTPException: 401 if credentials are invalid.

    Todo:
        - Fetch the user row from the database by username.
        - Verify: ``_pwd_context.verify(form.password, user.hashed_password)``.
        - Call ``_create_access_token(...)`` and return the token.
    """
    # Stub: always reject until the database is wired up.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication not yet configured",
    )


@_router.post("/logout")
async def logout(token: str = Depends(_oauth2_scheme)) -> dict[str, str]:
    """Invalidate the current access token.

    Args:
        token: The Bearer token from the ``Authorization`` header.

    Returns:
        A dict with a ``"status": "logged_out"`` key.

    Todo:
        Add the token ``jti`` (JWT ID) to a server-side blocklist (Redis or
        DB table) so that it cannot be reused before expiry.
    """
    return {"status": "logged_out"}  # TODO: implement token blocklist


# ── Capability implementations ────────────────────────────────────────────────


class PasswordAuthProvider:
    """Authenticates users with a username/password credential pair.

    Implements :class:`~strata.plugins.protocols.AuthProvider`.

    Attributes:
        id: ``"password"``
        name: ``"Username & Password"``
    """

    id: str = "password"
    name: str = "Username & Password"

    async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
        """Validate username/password credentials against the user database.

        Args:
            credentials: Dict with ``"username"`` and ``"password"`` keys.

        Returns:
            An :class:`~strata.plugins.protocols.AuthUser` on success, or
            ``None`` if the credentials dict does not contain the expected
            keys (letting other providers try).

        Raises:
            HTTPException: 401 if username/password are present but wrong.

        Todo:
            Fetch user from DB, verify password hash, return ``AuthUser``.
        """
        if "username" not in credentials or "password" not in credentials:
            return None
        # TODO: fetch from DB, verify hash, return AuthUser or raise 401.
        return None


class JwtAuthRouteProvider:
    """Contributes the register / login / logout API routes.

    Implements :class:`~strata.plugins.protocols.RouteProvider`.
    """

    def get_router(self) -> APIRouter:
        """Return the JWT auth API router.

        Returns:
            The configured ``fastapi.APIRouter``.
        """
        return _router


# ── Plugin ────────────────────────────────────────────────────────────────────


class JwtAuthPlugin(BackendPlugin):
    """Plugin providing JWT-based username/password authentication.

    Capabilities contributed:

    - ``registry.auth``: :class:`PasswordAuthProvider`
    - ``registry.routes``: :class:`JwtAuthRouteProvider`
    """

    id = "jwt_auth"
    name = "JWT Auth"
    version = "0.1.0"
    description = "Username/password login with JWT access tokens."

    def register(self, registry: PluginRegistry) -> None:
        """Contribute auth capabilities to the registry.

        Args:
            registry: The application-wide plugin registry.
        """
        registry.auth.add(PasswordAuthProvider())
        registry.routes.add(JwtAuthRouteProvider())

    async def on_startup(self) -> None:
        """Create the auth database directory if it does not exist.

        Todo:
            Run Alembic migrations to create/update the ``users`` table.
        """
        db_path = _AUTH_DB_URL.replace("sqlite+aiosqlite:///", "")
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


plugin = JwtAuthPlugin()
