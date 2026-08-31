from fastapi.testclient import TestClient
from sqlmodel import Session

import app.main as main
from app.config import Settings, get_settings
from app.db import create_db_and_tables, create_db_engine
from app.models import ServiceState
from tests.conftest import authenticate_client

app = main.app


def test_health_returns_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "agentgate-api"}


def test_meta_returns_provider_without_secret_material(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)
    response = client.get("/api/meta")

    assert response.status_code == 200
    assert response.json() == {
        "provider": get_settings().llm_provider,
        "model": get_settings().llm_model,
        "status": "ok",
    }
    assert "api_key" not in response.text


def test_development_startup_seeds_demo_service_state(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    monkeypatch.setattr(
        main,
        "settings",
        Settings.model_construct(environment="development", seed_demo=True),
    )

    with TestClient(app):
        with Session(engine) as session:
            payments = session.get(ServiceState, "payments-api")

    assert payments is not None
    assert payments.health == "degraded"


def test_production_startup_does_not_seed_demo_service_state(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    monkeypatch.setattr(
        main,
        "settings",
        Settings.model_construct(environment="production", seed_demo=False),
    )

    with TestClient(app):
        with Session(engine) as session:
            payments = session.get(ServiceState, "payments-api")

    assert payments is None
