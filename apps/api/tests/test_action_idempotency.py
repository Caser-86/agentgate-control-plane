from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.db import create_db_and_tables, create_db_engine
from app.files.models import ManagedWorkspace
from app.schemas_actions import ExternalActionRequest
from app.services.file_actions import ExternalActionError, ExternalActionService


@pytest.fixture
def session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as database_session:
        workspace = ManagedWorkspace(
            id=uuid4(),
        name="测试工作区",
            root_path=str(tmp_path),
            canonical_root_path=str(tmp_path),
            quarantine_root_path=str(tmp_path.parent / "quarantine"),
            protected_patterns=[".env"],
            enabled=True,
            version=1,
        )
        database_session.add(workspace)
        database_session.commit()
        yield database_session


@pytest.fixture
def workspace_id(session: Session):
    return session.exec(select(ManagedWorkspace.id)).one()


def test_reusing_key_with_different_arguments_is_rejected(session: Session, workspace_id) -> None:
    client_id = uuid4()
    service = ExternalActionService(session)
    service.propose(
        client_id,
        ExternalActionRequest(
            action="file.inspect.v1", workspace_id=workspace_id, relative_path="a.txt"
        ),
        "same-key-different-request",
    )

    with pytest.raises(ExternalActionError, match="idempotency_key_reused"):
        service.propose(
            client_id,
            ExternalActionRequest(
                action="file.inspect.v1", workspace_id=workspace_id, relative_path="b.txt"
            ),
            "same-key-different-request",
        )
