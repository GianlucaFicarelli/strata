"""Application settings."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_prefix="STRATA_")

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

    # Required: 32-byte URL-safe base64 key for AES-256-GCM field encryption.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Must be set if any StorageTemplate declares secret fields.
    ENCRYPTION_KEY: str = ""

    ENTRY_POINT_GROUP: str = "strata.plugins"
    ENABLED_PLUGINS: list[str] = [
        "storage_local",
        "storage_smb",
        "storage_s3",
        "image_preview",
        # "collabora",
        "auth_jwt",
        # "search_fulltext",
    ]

    @model_validator(mode="after")
    def _require_encryption_key(self) -> "Settings":
        # Validated lazily at startup once templates are registered.
        # See strata.main for the deferred check.
        return self


settings = Settings()
