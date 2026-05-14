import pytest
from strata_jwt_auth.config import settings

from tests.plugins.jwt_auth.utils import (
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_REFRESH_EXPIRE_DAYS,
    JWT_SECRET,
)


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", JWT_SECRET)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", JWT_ALGORITHM)
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", JWT_EXPIRE_MINUTES)
    monkeypatch.setattr(settings, "JWT_REFRESH_EXPIRE_DAYS", JWT_REFRESH_EXPIRE_DAYS)
