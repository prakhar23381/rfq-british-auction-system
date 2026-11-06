"""Column helpers shared by the ORM models."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    """UUID primary key, generated in Python (so it is known before flush) with a DB default."""
    return mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Native PostgreSQL enum whose labels are the StrEnum values."""
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])
