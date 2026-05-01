"""Application settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_prefix="STRATA_")

    ROOT_DIR: Path = Path("/strata")
    LOCAL_ROOT: Path = Path.home()
    COLLABORA_URL: str = "http://collabora:9980"
    COLLABORA_SECRET: str = "change-me"  # noqa: S105
    S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"


settings = Settings()
