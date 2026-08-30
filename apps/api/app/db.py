from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

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
    SQLModel.metadata.create_all(engine)


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
