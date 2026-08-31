import os
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError, ProgrammingError


def safe_test_database_url(raw_url: str) -> URL:
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("AGENTGATE_TEST_DATABASE_URL must use PostgreSQL")
    if url.host not in {"127.0.0.1", "::1", "localhost"}:
        pytest.fail("AGENTGATE_TEST_DATABASE_URL must use a loopback host")
    if url.database != "agentgate_test":
        pytest.fail("AGENTGATE_TEST_DATABASE_URL must use an agentgate_test database")
    return url


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("postgresql+psycopg://agentgate:test@db.example/agentgate_test", "loopback"),
        ("postgresql+psycopg://agentgate:test@localhost/agentgate", "agentgate_test"),
        ("postgresql+psycopg://agentgate:test@localhost/agentgate_test_dev", "agentgate_test"),
    ],
)
def test_test_database_url_rejects_unsafe_targets(url: str, message: str) -> None:
    with pytest.raises(pytest.fail.Exception, match=message):
        safe_test_database_url(url)


@pytest.fixture
def postgres_url() -> Generator[str, None, None]:
    raw_url = os.environ.get("AGENTGATE_TEST_DATABASE_URL")
    if raw_url is None:
        pytest.skip("AGENTGATE_TEST_DATABASE_URL is required for PostgreSQL migration tests")

    admin_url = safe_test_database_url(raw_url)
    temporary_database = f"agentgate_test_migration_{uuid4().hex}"
    admin_engine = create_engine(admin_url)
    autocommit_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    created = False
    try:
        try:
            with autocommit_engine.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{temporary_database}"'))
            created = True
        except (OperationalError, ProgrammingError) as error:
            pytest.skip(
                f"cannot create isolated PostgreSQL test database: {error.__class__.__name__}"
            )

        yield admin_url.set(database=temporary_database).render_as_string(hide_password=False)
    finally:
        if created:
            with autocommit_engine.connect() as connection:
                connection.execute(
                    text(f'DROP DATABASE IF EXISTS "{temporary_database}" WITH (FORCE)')
                )
        admin_engine.dispose()


def test_migration_head_creates_legacy_tables(postgres_url: str) -> None:
    from app.db import upgrade_to_head

    upgrade_to_head(postgres_url)
    engine = create_engine(postgres_url)
    try:
        inspector = inspect(engine)

        assert inspector.has_table("agent_runs")
        assert inspector.has_table("tool_actions")
        assert inspector.has_table("audit_events")
        assert inspector.has_table("service_states")
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
        script = ScriptDirectory.from_config(
            Config(str(Path(__file__).parents[1] / "alembic.ini"))
        )
        assert revision == script.get_current_head()
    finally:
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
