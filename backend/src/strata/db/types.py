from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, TypeDecorator


class TZDateTime(TypeDecorator[datetime]):
    """Convert timezone aware timestamps into timezone naive and back again.

    Adapted from:
    https://docs.sqlalchemy.org/en/21/core/custom_types.html#store-timezone-aware-timestamps-as-timezone-naive-utc
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is not None:
            if not value.tzinfo or value.tzinfo.utcoffset(value) is None:
                raise TypeError("tzinfo is required")
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is not None:
            value = value.replace(tzinfo=UTC)
        return value
