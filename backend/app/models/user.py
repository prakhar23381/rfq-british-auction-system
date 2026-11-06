import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.domain.enums import UserRole
from app.models.base import created_at_column, pg_enum, uuid_pk


class User(Base):
    """A seeded buyer or supplier. There is no login; the acting user is sent per request."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    def __repr__(self) -> str:
        return f"<User {self.company_name} ({self.role})>"
