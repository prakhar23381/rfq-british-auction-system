from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings, read from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "British Auction RFQ"
    database_url: str = "postgresql+psycopg://auction:auction@localhost:5432/british_auction"
    test_database_url: str = (
        "postgresql+psycopg://auction:auction@localhost:5432/british_auction_test"
    )
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:5173"]
    currency: str = "INR"
    log_level: str = "INFO"
    # How often Celery Beat runs the lifecycle sweeper.
    lifecycle_sweep_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
