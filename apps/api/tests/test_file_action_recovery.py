from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.control.enums import TaskStatus
from app.control.models import ControlTask
from app.db import create_db_and_tables, create_db_engine
from app.files.models import ManagedWorkspace
from app.models import ActionStatus, ToolAction
from app.schemas_actions import ExternalActionRequest
from app.services.approvals import ApprovalService
from app.services.file_actions import ExternalActionService, reconcile_file_action


@pytest.fixture
def session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as database_session:
        database_session.add(
            ManagedWorkspace(
                id=uuid4(),
                name="恢复工作区",
                root_path=str(tmp_path / "workspace"),
                canonical_root_path=str(tmp_path / "workspace"),
                quarantine_root_path=str(tmp_path / "quarantine"),
                protected_patterns=[".env"],
                enabled=True,
                version=1,
            )
        )
        database_session.commit()
        yield database_session


@pytest.mark.asyncio
async def test_running_file_action_recovery_stops_and_requires_manual_review(
    session: Session,
) -> None:
    workspace = session.exec(select(ManagedWorkspace)).one()
    proposed = ExternalActionService(session).propose(
        uuid4(),
        ExternalActionRequest(
            action="file.quarantine.v1", workspace_id=workspace.id, relative_path="demo.txt"
        ),
        "recovery-running-1",
    )
    action = session.get(ToolAction, proposed.id)
    assert action is not None
    await ApprovalService(session).approve(action.id, actor="operator:test")
    task = session.exec(select(ControlTask)).one()
    task.status = TaskStatus.RUNNING
    task.lease_owner_id = uuid4()
    task.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    session.add(task)
    session.commit()

    result = reconcile_file_action(session, action.id)

    assert result.decision == "manual_review_required"
    session.expire_all()
    saved_task = session.get(ControlTask, task.id)
    saved_action = session.get(ToolAction, action.id)
    assert saved_task is not None and saved_task.status == TaskStatus.MANUAL_REVIEW
    assert saved_action is not None and saved_action.status == ActionStatus.FAILED


@pytest.mark.asyncio
async def test_queued_file_action_recovery_is_safe_to_retry(session: Session) -> None:
    workspace = session.exec(select(ManagedWorkspace)).one()
    proposed = ExternalActionService(session).propose(
        uuid4(),
        ExternalActionRequest(
            action="file.quarantine.v1", workspace_id=workspace.id, relative_path="demo.txt"
        ),
        "recovery-queued-1",
    )
    action = session.get(ToolAction, proposed.id)
    assert action is not None
    await ApprovalService(session).approve(action.id, actor="operator:test")

    result = reconcile_file_action(session, action.id)

    assert result.decision == "retry_safe"
    session.expire_all()
    saved_action = session.get(ToolAction, action.id)
    assert saved_action is not None and saved_action.status == ActionStatus.APPROVED
