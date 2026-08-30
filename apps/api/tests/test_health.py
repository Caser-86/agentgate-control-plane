from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.main import app
from app.models import ServiceState


def test_health_returns_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "agentgate-api"}


def test_startup_initializes_demo_service_state() -> None:
    with TestClient(app):
        with Session(get_engine()) as session:
            payments = session.get(ServiceState, "payments-api")

    assert payments is not None
    assert payments.health == "degraded"
