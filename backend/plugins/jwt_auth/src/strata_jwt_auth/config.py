from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Plugin settings."""

    model_config = SettingsConfigDict(env_prefix="STRATA_")

    JWT_SECRET: str = "guWcsyd9RSK6aaDzNpqssdA4CkZAHH"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 15
    AUTH_DB_URL: str = f"sqlite+aiosqlite:///{Path('~').expanduser()}/.strata/auth.db"


settings = Settings()
