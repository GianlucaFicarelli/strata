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

from strata_jwt_auth.plugin import plugin

__all__ = ["plugin"]
