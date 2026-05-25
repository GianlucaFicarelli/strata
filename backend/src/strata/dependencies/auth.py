"""Authentication dependencies.

The core authentication dependencies read the session cookie set by whichever
auth plugin is active (e.g. ``auth_local``).  The cookie value is an opaque
session ID; the actual user data is retrieved from Redis via
:class:`~strata.sessions.service.SessionService`.

Two variants are provided:

:data:`OptionalCurrentUserDep`
    Resolves to the authenticated :class:`~strata.schemas.auth.AuthUser` if a
    valid session cookie is present, or ``None`` otherwise.  Use for endpoints
    that serve both anonymous and authenticated callers.

:data:`CurrentUserDep`
    Like ``OptionalCurrentUserDep`` but raises **HTTP 401** when no valid
    session is present.  Use for all endpoints that require authentication.

The core never imports any specific auth plugin.  Session storage and retrieval
are handled entirely by :class:`~strata.sessions.service.SessionService`.
"""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from strata.config import settings
from strata.schemas.auth import AuthUser
from strata.sessions.deps import SessionServiceDep
from strata.sessions.service import SessionService


async def _optional_current_user(
    session_service: SessionServiceDep,
    session_id: Annotated[str | None, Cookie(alias=settings.SESSION_COOKIE_NAME)] = None,
) -> AuthUser | None:
    """Return the authenticated user from the session cookie, or None.

    Args:
        session_service: Application-wide Redis-backed session service.
        session_id: Value of the ``strata_session`` HttpOnly cookie.

    Returns:
        :class:`~strata.schemas.auth.AuthUser` if the session is valid,
        ``None`` if the cookie is absent or the session has expired.
    """
    if not session_id:
        return None
    data = await session_service.get(session_id)
    if data is None:
        return None
    return AuthUser(
        id=data.user_id,
        username=data.username,
        display_name=data.display_name,
        email=data.email,
        is_admin=data.is_admin,
    )


async def _require_current_user(
    user: Annotated[AuthUser | None, Depends(_optional_current_user)],
) -> AuthUser:
    """Return the authenticated user or raise HTTP 401.

    Args:
        user: Result of ``_optional_current_user``.

    Returns:
        The authenticated :class:`~strata.schemas.auth.AuthUser`.

    Raises:
        HTTPException: 401 if no valid session cookie is present.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def session_cookie_helper(response: object, session_id: str, service: SessionService) -> None:
    """Attach the session cookie to *response*.

    Extracted here so auth plugins can call it without importing FastAPI
    response internals directly.  Kept in the auth module because cookie
    attributes are a security concern owned by core, not plugins.

    Args:
        response: A FastAPI :class:`fastapi.Response` instance.
        session_id: The opaque session ID to set as the cookie value.
        service: Unused here but kept in signature for future TTL sync.
    """
    # Import here to avoid circular import at module load time.
    from fastapi import Response  # noqa: PLC0415

    assert isinstance(response, Response)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/api",
        max_age=settings.SESSION_TTL_SECONDS,
    )


def clear_session_cookie(response: object) -> None:
    """Expire the session cookie on *response* (used on logout).

    Args:
        response: A FastAPI :class:`fastapi.Response` instance.
    """
    from fastapi import Response  # noqa: PLC0415

    assert isinstance(response, Response)
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/api",
    )


OptionalCurrentUserDep = Annotated[AuthUser | None, Depends(_optional_current_user)]
CurrentUserDep = Annotated[AuthUser, Depends(_require_current_user)]
