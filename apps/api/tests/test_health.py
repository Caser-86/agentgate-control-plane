from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import get_settings
from app.db import get_engine
from app.main import app
from app.models import ServiceState


def test_health_returns_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "agentgate-api"}


def test_meta_returns_provider_without_secret_material() -> None:
    response = TestClient(app).get("/api/meta")

    assert response.status_code == 200
    assert response.json() == {
        "provider": get_settings().llm_provider,
        "model": get_settings().llm_model,
        "status": "ok",
    }
    assert "api_key" not in response.text


def test_startup_initializes_demo_service_state() -> None:
    with TestClient(app):
        with Session(get_engine()) as session:
            payments = session.get(ServiceState, "payments-api")

    assert payments is not None
    assert payments.health == "degraded"
