"""JWT-based password authentication plugin for Strata.

Contributes:

- :class:`~strata.plugins.protocols.DbContributor`: declares the
  ``auth_jwt_users`` and ``auth_jwt_refresh_tokens`` tables and the Alembic
  migrations directory so the shared engine automatically runs
  ``upgrade head`` at startup.
- :class:`~strata.plugins.protocols.AuthProvider`: validates
  username/password credentials against the local user store and returns an
  :class:`~strata.plugins.protocols.AuthUser`.
- :class:`~strata.plugins.protocols.RouteProvider`: exposes:

  - ``POST /api/plugins/auth_jwt/register``
  - ``POST /api/plugins/auth_jwt/login``
  - ``POST /api/plugins/auth_jwt/refresh``
  - ``POST /api/plugins/auth_jwt/logout``
  - ``GET  /api/plugins/auth_jwt/me``

Entry point::

    [project.entry-points."strata.plugins"]
    auth_jwt = "strata_auth_jwt:plugin"

Configuration (all optional — set in ``.env`` or environment):

.. code-block:: bash

    STRATA_DB_URL="sqlite+aiosqlite:///$HOME/.strata/strata.db"  # from core
    STRATA_JWT_SECRET="<long-random-hex>"
    STRATA_JWT_EXPIRE_MINUTES=15
    STRATA_JWT_REFRESH_EXPIRE_DAYS=30

Security:
    Passwords are hashed with Argon2id via pwdlib.  Access tokens are
    short-lived JWTs (HS256).  Refresh tokens are random 32-byte values
    stored as SHA-256 hashes; they are rotated on every use.
"""

from strata_auth_jwt.plugin import plugin

__all__ = ["plugin"]
