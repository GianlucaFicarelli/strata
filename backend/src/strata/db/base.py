from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from strata.db.types import TZDateTime


class Base(DeclarativeBase):
    """Common declarative base."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: TZDateTime,
    }
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
