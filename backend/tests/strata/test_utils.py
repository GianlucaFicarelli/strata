"""Unit tests for strata.utils."""

import uuid
from datetime import UTC

from strata.utils import create_uuid, utcnow


def test_create_uuid_is_valid_uuid4():
    value = create_uuid()
    parsed = uuid.UUID(value)
    assert parsed.version == 4


def test_create_uuid_returns_string():
    assert isinstance(create_uuid(), str)


def test_create_uuid_unique():
    assert create_uuid() != create_uuid()


def test_utcnow_is_timezone_aware():
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0


def test_utcnow_timezone_is_utc():
    now = utcnow()
    assert now.tzinfo == UTC
