from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Deterministic names for constraints SQLAlchemy creates implicitly (PK, FK, unique).
# Check constraints and indexes are always named explicitly in the models.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Sessions run in UTC so timestamps come back as UTC regardless of the server's default zone.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"options": "-c timezone=utc"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session that is always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
