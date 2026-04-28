"""Application settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    ROOT_DIR: Path = Path("/strata")


settings = Settings()
