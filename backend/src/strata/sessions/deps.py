"""FastAPI dependencies for the session layer."""

from typing import Annotated

from fastapi import Depends, Request

from strata.sessions.service import SessionService


async def _session_service_dep(request: Request) -> SessionService:
    """Resolve the application-wide :class:`~strata.sessions.service.SessionService`.

    The instance is stored on ``app.state.session_service`` during lifespan
    startup and is available for the full application lifetime.

    Args:
        request: The current HTTP request (provides access to ``app.state``).

    Returns:
        The singleton :class:`~strata.sessions.service.SessionService`.
    """
    service: SessionService = request.app.state.session_service
    return service


SessionServiceDep = Annotated[SessionService, Depends(_session_service_dep)]
