import os
from collections.abc import Generator
from uuid import uuid4

os.environ.setdefault("AGENTGATE_LLM_PROVIDER", "mock")
os.environ.setdefault("AGENTGATE_DATABASE_URL", "sqlite://")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlmodel import Session

from tests.test_migrations import safe_test_database_url


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
