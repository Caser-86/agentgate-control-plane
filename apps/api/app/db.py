from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.auth.models  # noqa: F401
import app.control.models  # noqa: F401
import app.files.models  # noqa: F401
import app.monitoring.models  # noqa: F401
from app.config import get_settings
from app.models import ServiceState


def create_db_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs: dict[str, object] = {"echo": False, "connect_args": connect_args}
    if url in {"sqlite://", "sqlite:///:memory:"}:
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


@lru_cache
def get_engine() -> Engine:
    return create_db_engine(get_settings().database_url)


def create_db_and_tables(engine: Engine) -> None:
    """Create SQLite tables for isolated unit-test engines only."""
    SQLModel.metadata.create_all(engine)


def reset_db_and_tables(engine: Engine) -> None:
    """Reset the disposable SQLite database used by a bounded E2E project."""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def _alembic_config(database_url: str) -> Config:
    api_root = Path(__file__).resolve().parent.parent
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str) -> None:
    """Run Alembic upgrade head for an explicit database URL."""
    command.upgrade(_alembic_config(database_url), "head")


def database_schema_is_ready(engine: Engine) -> bool:
    """Return whether the database records the current Alembic head revision."""
    config = _alembic_config(str(engine.url))
    script = ScriptDirectory.from_config(config)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision() == script.get_current_head()


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def seed_demo_state(session: Session) -> None:
    defaults = (
        ServiceState(service="payments-api", health="degraded", restart_count=0),
        ServiceState(service="orders-api", health="healthy", restart_count=0),
    )
    for default in defaults:
        existing = session.get(ServiceState, default.service)
        if existing is None:
            session.add(default)
    session.commit()
