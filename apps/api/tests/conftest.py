import os
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("AGENTGATE_LLM_PROVIDER", "mock")
os.environ.setdefault("AGENTGATE_DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlmodel import Session

from app.auth.security import ensure_bootstrap_token
from app.config import get_settings
from app.db import create_db_and_tables, create_db_engine, get_session
from app.main import app
from tests.test_migrations import safe_test_database_url


@pytest.fixture(autouse=True)
def auth_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep security regression tests independent from a developer's local .env."""
    monkeypatch.setattr(get_settings(), "auth_enabled", True)


@pytest.fixture
def auth_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, object, Path], None, None]:
    """A real SQLite-backed first-run browser client with a disposable enrollment file."""
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    token_file = tmp_path / "bootstrap-token"
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_bootstrap_token_file", str(token_file))
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    with Session(engine) as session:
        ensure_bootstrap_token(session, settings)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, engine, token_file
    app.dependency_overrides.clear()


def authenticate_client(client: TestClient, token_file: Path) -> None:
    """Create the single operator and install its CSRF header for browser-route tests."""
    setup = client.post(
        "/api/auth/setup",
        json={
            "bootstrap_token": token_file.read_text(encoding="utf-8"),
            "password": "password-placeholder",
        },
    )
    assert setup.status_code == 201
    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    client.headers.update(
        {"Origin": "http://localhost:5173", "X-CSRF-Token": csrf.json()["csrf_token"]}
    )


@pytest.fixture
def postgres_session_pair() -> Generator[tuple[Session, Session], None, None]:
    """Provide two independent sessions against an isolated loopback PostgreSQL database."""
    raw_url = os.environ.get("AGENTGATE_TEST_DATABASE_URL")
    if raw_url is None:
        pytest.skip("AGENTGATE_TEST_DATABASE_URL is required for PostgreSQL queue tests")
    admin_url = safe_test_database_url(raw_url)
    database_name = f"agentgate_test_control_{uuid4().hex}"
    admin_engine = create_engine(admin_url)
    autocommit_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    database_created = False
    engine = None
    try:
        try:
            with autocommit_engine.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            database_created = True
        except (OperationalError, ProgrammingError) as error:
            pytest.skip(
                f"cannot create isolated PostgreSQL test database: {error.__class__.__name__}"
            )
        database_url = admin_url.set(database=database_name).render_as_string(hide_password=False)
        from app.db import upgrade_to_head

        upgrade_to_head(database_url)
        engine = create_engine(database_url)
        with Session(engine) as session_a, Session(engine) as session_b:
            yield session_a, session_b
    finally:
        if engine is not None:
            engine.dispose()
        if database_created:
            with autocommit_engine.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()
