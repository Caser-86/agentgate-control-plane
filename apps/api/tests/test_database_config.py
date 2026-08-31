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


def test_local_ports_drive_api_base_url_and_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTGATE_API_PORT", "18000")
    monkeypatch.setenv("AGENTGATE_WEB_PORT", "15173")
    monkeypatch.delenv("AGENTGATE_WEB_ORIGIN", raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()

        assert settings.api_base_url == "http://localhost:18000"
        assert settings.web_origin == "http://localhost:15173"
    finally:
        get_settings.cache_clear()
