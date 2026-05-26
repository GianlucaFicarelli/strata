"""Application settings."""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_prefix="STRATA_",
        env_file=".env",
    )

    APP_NAME: str = "Strata"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "A plugin-based file browser with swappable storage backends."
    ROOT_DIR: Path = Path("/strata")
    LOCAL_ROOT: Path = Path.home()
    COLLABORA_URL: str = "http://collabora:9980"
    COLLABORA_SECRET: str = "change-me"
    S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"

    DB_URL: str = f"sqlite+aiosqlite:///{Path('~').expanduser()}/.strata/strata.db"
    DB_ECHO: bool = False

    # Required: 32-byte URL-safe base64 key for AES-256-GCM field encryption
    # and HMAC signing of download tokens.
    # Generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Must be set if any StorageTemplate declares secret fields.
    ENCRYPTION_KEY: str = ""

    # Redis session store
    REDIS_URL: str = "redis://localhost:6379/0"
    SESSION_TTL_SECONDS: int = 7 * 86_400  # 7 days; renewed on every request
    SESSION_COOKIE_NAME: str = "strata_session"
    SESSION_COOKIE_SECURE: bool = True  # set False for local HTTP dev
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "strict"

    # Download token (HMAC-signed, stateless)
    DOWNLOAD_TOKEN_TTL_SECONDS: int = 300  # 5 minutes

    # Comma-separated list of origins allowed to make credentialed requests.
    # In production set this to the exact origin of the frontend, e.g.
    # STRATA_ALLOWED_ORIGINS=https://strata.example.com
    # During local development the Vite dev server runs on a different port,
    # so add http://localhost:5173 here.
    # The wildcard "*" cannot be used together with credentials=true (browsers
    # reject it), so an explicit list is always required.
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8000"]

    ENTRY_POINT_GROUP: str = "strata.plugins"
    ENABLED_PLUGINS: list[str] = [
        "storage_local",
        "storage_smb",
        "storage_s3",
        "image_preview",
        # "collabora",
        "auth_local",
        # "search_fulltext",
    ]

    @model_validator(mode="after")
    def _require_encryption_key(self) -> Self:
        # Validated lazily at startup once templates are registered.
        # See strata.main for the deferred check.
        return self


settings = Settings()
