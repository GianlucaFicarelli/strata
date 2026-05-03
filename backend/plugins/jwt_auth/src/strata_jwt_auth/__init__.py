"""JWT-based password authentication plugin for Strata.

Contributes:

- :class:`~strata.plugins.protocols.DbContributor`: declares the
  ``jwt_auth_users`` and ``jwt_auth_refresh_tokens`` tables and the Alembic
  migrations directory so the shared engine automatically runs
  ``upgrade head`` at startup.
- :class:`~strata.plugins.protocols.AuthProvider`: validates
  username/password credentials against the local user store and returns an
  :class:`~strata.plugins.protocols.AuthUser`.
- :class:`~strata.plugins.protocols.RouteProvider`: exposes:

  - ``POST /api/plugins/jwt_auth/register``
  - ``POST /api/plugins/jwt_auth/login``
  - ``POST /api/plugins/jwt_auth/refresh``
  - ``POST /api/plugins/jwt_auth/logout``
  - ``GET  /api/plugins/jwt_auth/me``

Entry point::

    [project.entry-points."strata.plugins"]
    jwt_auth = "strata_jwt_auth:plugin"

Configuration (all optional — set in ``.env`` or environment):

.. code-block:: bash

    STRATA_DB_URL="sqlite+aiosqlite:///$HOME/.strata/strata.db"  # from core
    STRATA_JWT_SECRET="<long-random-hex>"
    STRATA_JWT_EXPIRE_MINUTES=15
    STRATA_JWT_REFRESH_EXPIRE_DAYS=30

Security:
    Passwords are hashed with Argon2id via passlib.  Access tokens are
    short-lived JWTs (HS256).  Refresh tokens are random 32-byte values
    stored as SHA-256 hashes; they are rotated on every use.
"""

from strata_jwt_auth.plugin import plugin

__all__ = ["plugin"]
