import pytest

from app.config import get_settings


def test_postgres_url_is_the_compose_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENTGATE_DATABASE_URL",
        "postgresql+psycopg://agentgate:test@postgres/agentgate",
    )
    get_settings.cache_clear()

    assert get_settings().database_url.startswith("postgresql+psycopg://")


def test_database_url_defaults_to_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTGATE_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    assert get_settings().database_url == (
        "postgresql+psycopg://agentgate:agentgate@postgres:5432/agentgate"
    )
