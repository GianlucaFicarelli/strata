"""Settings for the JWT auth plugin.

All variables use the ``STRATA_`` prefix so they sit alongside the core
settings in a single ``.env`` file.

Variables
---------
STRATA_JWT_SECRET
    Secret key used to sign access tokens.  **Must** be a long random string
    in production.  Generate one with::

        python -c "import secrets; print(secrets.token_hex(32))"

STRATA_JWT_ALGORITHM
    HMAC algorithm for PyJWT.  ``"HS256"`` is the default; ``"HS512"`` is
    a reasonable upgrade for higher-security deployments.

STRATA_JWT_EXPIRE_MINUTES
    Lifetime of an access token in minutes.  Short (≤15 min) is recommended;
    refresh tokens handle session continuity.

STRATA_JWT_REFRESH_EXPIRE_DAYS
    Lifetime of a refresh token in days.  Refresh tokens are stored server-side
    (``jwt_auth_refresh_tokens`` table) and can be revoked immediately.

Note: the database URL is **not** configured here.  The plugin uses the
shared ``STRATA_DB_URL`` from the core :mod:`strata.config` settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """JWT auth plugin settings."""

    model_config = SettingsConfigDict(env_prefix="STRATA_")

    JWT_SECRET: str = "change-me-use-secrets-token-hex-32-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 30


settings = Settings()
