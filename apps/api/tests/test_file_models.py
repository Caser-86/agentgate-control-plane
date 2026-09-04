from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine
from app.files.models import ManagedWorkspace, QuarantineEntry


@pytest.fixture
def engine() -> Engine:
    test_engine = create_db_engine("sqlite://")
    create_db_and_tables(test_engine)
    return test_engine


def test_workspace_version_and_quarantine_status_are_persistable(engine: Engine) -> None:
    workspace = ManagedWorkspace(
        id=uuid4(),
        name="演示工作区",
        root_path=r"D:\demo",
        canonical_root_path=r"D:\demo",
        quarantine_root_path=r"D:\demo-quarantine",
        protected_patterns=[".git/**"],
        enabled=True,
        version=1,
    )
    entry = QuarantineEntry(
        id=uuid4(),
        workspace_id=workspace.id,
        action_id=uuid4(),
        original_relative_path="notes.txt",
        quarantine_relative_path="entries/notes.txt",
        content_sha256="a" * 64,
        size_bytes=1,
        status="quarantined",
    )

    with Session(engine) as session:
        session.add(workspace)
        session.commit()
        session.add(entry)
        session.commit()

        saved_workspace = session.get(ManagedWorkspace, workspace.id)
        saved_entry = session.get(QuarantineEntry, entry.id)

    assert saved_workspace is not None
    assert saved_workspace.version == 1
    assert saved_entry is not None
    assert saved_entry.status == "quarantined"
