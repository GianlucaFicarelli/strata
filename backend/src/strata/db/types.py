import datetime

from sqlalchemy import DateTime, TypeDecorator


class TZDateTime(TypeDecorator):
    """Convert timezone aware timestamps into timezone naive and back again.

    Adapted from:
    https://docs.sqlalchemy.org/en/21/core/custom_types.html#store-timezone-aware-timestamps-as-timezone-naive-utc
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not value.tzinfo or value.tzinfo.utcoffset(value) is None:
                raise TypeError("tzinfo is required")
            value = value.astimezone(datetime.UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=datetime.UTC)
        return value
