import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@db:5432/x", "postgresql+psycopg://u:p@db:5432/x"),
        ("postgresql://u:p@db/x", "postgresql+psycopg://u:p@db/x"),
        ("postgresql+psycopg://u:p@db/x", "postgresql+psycopg://u:p@db/x"),
    ],
)
def test_provider_database_urls_get_the_psycopg_driver(given: str, expected: str) -> None:
    settings = Settings(database_url=given, test_database_url=given)
    assert settings.database_url == expected
    assert settings.test_database_url == expected
