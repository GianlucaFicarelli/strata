from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from strata_jwt_auth.schemas import RegisterRequest, TokenResponse

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/plugins/jwt_auth/login")
plugin_router = APIRouter(prefix="/api/plugins/jwt_auth", tags=["auth"])


@plugin_router.post("/register", status_code=status.HTTP_201_CREATED)
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


@plugin_router.post("/login", response_model=TokenResponse)
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


@plugin_router.post("/logout")
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
