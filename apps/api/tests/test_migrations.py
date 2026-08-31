import os
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlmodel import create_engine


@pytest.fixture
def postgres_url() -> Generator[str, None, None]:
    url = os.environ.get("AGENTGATE_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("AGENTGATE_TEST_DATABASE_URL is required for PostgreSQL migration tests")

    database_name = urlparse(url).path.removeprefix("/")
    if "test" not in database_name.lower():
        pytest.fail("AGENTGATE_TEST_DATABASE_URL must point to a dedicated test database")

    yield url


def test_migration_head_creates_legacy_tables(postgres_url: str) -> None:
    from app.db import upgrade_to_head

    upgrade_to_head(postgres_url)
    engine = create_engine(postgres_url)
    inspector = inspect(engine)

    assert inspector.has_table("agent_runs")
    assert inspector.has_table("tool_actions")
    assert inspector.has_table("audit_events")
    assert inspector.has_table("service_states")
    engine.dispose()


def test_baseline_migration_creates_each_postgres_enum_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://agentgate:test@localhost/agentgate_test"
    )

    command.upgrade(config, "head", sql=True)

    sql = capsys.readouterr().out
    for enum_name in ("runstatus", "actionstatus", "risklevel", "policydecision"):
        assert sql.count(f"CREATE TYPE {enum_name}") == 1
    assert "uq_tool_actions_idempotency_key" not in sql
    assert sql.count("CREATE UNIQUE INDEX ix_tool_actions_idempotency_key") == 1
