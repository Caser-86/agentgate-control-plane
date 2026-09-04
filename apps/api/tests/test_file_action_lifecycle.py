import hashlib
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.control.enums import TaskStatus
from app.control.models import ControlTask, WorkerExecutionGrant, WorkerRegistration
from app.db import create_db_and_tables, create_db_engine
from app.files.models import ManagedWorkspace, QuarantineEntry
from app.models import ActionStatus, PolicyDecision, RiskLevel, ToolAction
from app.schemas_actions import ExternalActionRequest
from app.services.approvals import ApprovalConflictError, ApprovalService
from app.services.file_actions import ExternalActionService
from app.services.worker_protocol import (
    PROTOCOL_VERSION,
    claim_worker_task,
    complete_worker_task,
    request_digest,
    start_worker_task,
)


@pytest.fixture
def session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as database_session:
        database_session.add(
            ManagedWorkspace(
                id=uuid4(),
                name="生命周期工作区",
                root_path=str(tmp_path / "workspace"),
                canonical_root_path=str(tmp_path / "workspace"),
                quarantine_root_path=str(tmp_path / "quarantine"),
                protected_patterns=[".env", "protected/**"],
                enabled=True,
                version=1,
            )
        )
        database_session.commit()
        yield database_session


def _workspace(session: Session) -> ManagedWorkspace:
    return session.exec(select(ManagedWorkspace)).one()


def _register_worker(session: Session, capabilities: list[str]) -> WorkerRegistration:
    worker = WorkerRegistration(
        id=uuid4(),
        name="lifecycle-worker",
        version="test",
        protocol_version=PROTOCOL_VERSION,
        capabilities=capabilities,
        token_digest=f"worker-{uuid4()}",
    )
    session.add(worker)
    session.commit()
    return worker


def _complete_file_task(
    session: Session, task: ControlTask, worker: WorkerRegistration, result: dict[str, object]
) -> ControlTask:
    claimed = claim_worker_task(
        session,
        worker_id=worker.id,
        protocol_version=PROTOCOL_VERSION,
        capabilities=worker.capabilities,
    )
    assert claimed is not None and claimed.id == task.id
    start_worker_task(
        session,
        task_id=task.id,
        worker_id=worker.id,
        protocol_version=PROTOCOL_VERSION,
        request_digest_value=request_digest(task),
    )
    return complete_worker_task(
        session,
        task_id=task.id,
        worker_id=worker.id,
        protocol_version=PROTOCOL_VERSION,
        request_digest_value=request_digest(task),
        result=result,
    )


@pytest.mark.asyncio
async def test_approval_creates_one_file_task_and_success_projects_entry(
    session: Session,
) -> None:
    workspace = _workspace(session)
    client_id = uuid4()
    proposed = ExternalActionService(session).propose(
        client_id,
        ExternalActionRequest(
            action="file.quarantine.v1",
            workspace_id=workspace.id,
            relative_path="demo.txt",
            reason="文件治理测试",
        ),
        "lifecycle-quarantine-1",
    )
    action = session.get(ToolAction, proposed.id)
    assert action is not None
    assert action.status == ActionStatus.PENDING_APPROVAL

    approved = await ApprovalService(session).approve(action.id, actor="operator:test")

    assert approved.status == ActionStatus.APPROVED
    task = session.exec(
        select(ControlTask).where(ControlTask.capability == "file.quarantine.v1")
    ).one()
    assert task.status == TaskStatus.QUEUED
    assert task.payload["action_id"] == str(action.id)
    assert session.exec(select(WorkerExecutionGrant)).all() == []

    worker = _register_worker(session, ["file.quarantine.v1"])
    digest = hashlib.sha256(b"demo").hexdigest()
    completed = _complete_file_task(
        session,
        task,
        worker,
        {
            "status": "succeeded",
            "result_kind": "file_quarantine",
            "side_effect": "quarantined",
            "content_sha256": digest,
            "size_bytes": 4,
            "quarantine_entry_id": str(action.id),
            "quarantine_relative_path": f"entries/{action.id.hex}/demo.txt",
        },
    )

    assert completed.status == TaskStatus.SUCCEEDED
    session.expire_all()
    saved_action = session.get(ToolAction, action.id)
    assert saved_action is not None
    assert saved_action.status == ActionStatus.SUCCEEDED
    entry = session.get(QuarantineEntry, action.id)
    assert entry is not None
    assert entry.status == "quarantined"
    assert entry.original_relative_path == "demo.txt"
    assert entry.content_sha256 == digest
    status = ExternalActionService(session).get_status(client_id, action.id)
    assert status.status == ActionStatus.SUCCEEDED.value
    assert status.result == {
        "status": "succeeded",
        "result_kind": "file_quarantine",
        "side_effect": "quarantined",
        "content_sha256": digest,
        "size_bytes": 4,
        "quarantine_entry_id": str(action.id),
        "quarantine_relative_path": f"entries/{action.id.hex}/demo.txt",
    }


@pytest.mark.asyncio
async def test_denial_of_external_file_action_is_terminal_without_task(session: Session) -> None:
    workspace = _workspace(session)
    proposed = ExternalActionService(session).propose(
        uuid4(),
        ExternalActionRequest(
            action="file.quarantine.v1", workspace_id=workspace.id, relative_path="demo.txt"
        ),
        "lifecycle-deny-1",
    )
    action = session.get(ToolAction, proposed.id)
    assert action is not None

    denied = await ApprovalService(session).deny(action.id, actor="operator:test")

    assert denied.status == ActionStatus.DENIED
    assert session.exec(select(ControlTask)).all() == []
    assert denied.run_id is None


@pytest.mark.asyncio
async def test_stale_workspace_version_blocks_approval_without_task(session: Session) -> None:
    workspace = _workspace(session)
    proposed = ExternalActionService(session).propose(
        uuid4(),
        ExternalActionRequest(
            action="file.quarantine.v1", workspace_id=workspace.id, relative_path="demo.txt"
        ),
        "lifecycle-stale-1",
    )
    workspace.version = 2
    session.add(workspace)
    session.commit()
    action = session.get(ToolAction, proposed.id)
    assert action is not None

    with pytest.raises(ApprovalConflictError, match="工作区版本"):
        await ApprovalService(session).approve(action.id, actor="operator:test")

    session.expire_all()
    saved_action = session.get(ToolAction, action.id)
    assert saved_action is not None
    assert saved_action.status == ActionStatus.PENDING_APPROVAL
    assert session.exec(select(ControlTask)).all() == []


@pytest.mark.asyncio
async def test_restore_conflict_is_terminal_and_never_overwrites_entry(session: Session) -> None:
    workspace = _workspace(session)
    client_id = uuid4()
    quarantine_action = ToolAction(
        id=uuid4(),
        run_id=None,
        proposer_client_id=client_id,
        tool_call_id=f"external:{uuid4()}",
        tool_name="file.quarantine.v1",
        target_type="managed_workspace",
        target_id=workspace.id,
        action_version="file.quarantine.v1",
        arguments_digest="a" * 64,
        policy_version="file-policy.v1",
        risk_level=RiskLevel.MEDIUM,
        policy_decision=PolicyDecision.REQUIRE_APPROVAL,
        status=ActionStatus.SUCCEEDED,
        arguments_json=(
            f'{{"workspace_id":"{workspace.id}","workspace_version":1,'
            '"relative_path":"demo.txt"}}'
        ),
        reason="已隔离",
        idempotency_key="previous-quarantine-1",
    )
    session.add(quarantine_action)
    session.flush()
    entry = QuarantineEntry(
        id=uuid4(),
        workspace_id=workspace.id,
        action_id=quarantine_action.id,
        original_relative_path="demo.txt",
        quarantine_relative_path=f"entries/{quarantine_action.id.hex}/demo.txt",
        content_sha256="b" * 64,
        size_bytes=4,
        status="quarantined",
    )
    session.add(entry)
    session.commit()

    proposed = ExternalActionService(session).propose(
        client_id,
        ExternalActionRequest(
            action="file.restore.v1",
            workspace_id=workspace.id,
            quarantine_entry_id=entry.id,
        ),
        "restore-conflict-1",
    )
    action = session.get(ToolAction, proposed.id)
    assert action is not None
    await ApprovalService(session).approve(action.id, actor="operator:test")
    task = session.exec(
        select(ControlTask).where(ControlTask.capability == "file.restore.v1")
    ).one()
    worker = _register_worker(session, ["file.restore.v1"])

    completed = _complete_file_task(
        session,
        task,
        worker,
        {
            "status": "failed",
            "result_kind": "file_restore",
            "side_effect": "conflict",
            "content_sha256": "b" * 64,
            "size_bytes": 4,
            "error_code": "destination_conflict",
            "error_message": "恢复目标已存在，未覆盖",
        },
    )

    assert completed.status == TaskStatus.FAILED
    session.expire_all()
    saved_action = session.get(ToolAction, action.id)
    saved_entry = session.get(QuarantineEntry, entry.id)
    assert saved_action is not None and saved_action.status == ActionStatus.FAILED
    assert saved_entry is not None and saved_entry.status == "quarantined"
