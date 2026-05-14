"""Application settings."""

from pathlib import Path

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

    ENTRY_POINT_GROUP: str = "strata.plugins"
    ENABLED_PLUGINS: list[str] = [
        "local_storage",
        "smb_storage",
        "s3_storage",
        "image_preview",
        # "collabora",
        "jwt_auth",
        # "search_fulltext",
    ]


settings = Settings()
