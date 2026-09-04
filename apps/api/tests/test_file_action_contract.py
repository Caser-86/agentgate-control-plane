import hashlib
import json
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask, WorkerRegistration
from app.db import create_db_and_tables, create_db_engine
from app.files.models import ManagedWorkspace, QuarantineEntry
from app.models import ActionStatus, ToolAction
from app.schemas_actions import ExternalActionRequest
from app.services.approvals import ApprovalService
from app.services.file_actions import ExternalActionService
from app.services.worker_protocol import (
    PROTOCOL_VERSION,
    claim_worker_task,
    complete_worker_task,
    request_digest,
    start_worker_task,
)


@pytest.fixture
def contract_session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    with Session(engine) as session:
        session.add(
            ManagedWorkspace(
                id=uuid4(),
                name="完整契约工作区",
                root_path=str(workspace_root),
                canonical_root_path=str(workspace_root),
                quarantine_root_path=str(tmp_path / "quarantine"),
                protected_patterns=[".env", ".env.*", "protected/**"],
                enabled=True,
                version=1,
            )
        )
        session.commit()
        yield session


def _workspace(session: Session) -> ManagedWorkspace:
    return session.exec(select(ManagedWorkspace)).one()


def _worker(session: Session) -> WorkerRegistration:
    worker = WorkerRegistration(
        id=uuid4(),
        name="契约 Worker",
        version="test",
        protocol_version=PROTOCOL_VERSION,
        capabilities=["file.quarantine.v1", "file.restore.v1"],
        token_digest=f"contract-{uuid4()}",
    )
    session.add(worker)
    session.commit()
    return worker


def _complete_next_file_task(
    session: Session, worker: WorkerRegistration, capability: str, result: dict[str, object]
) -> ControlTask:
    task = session.exec(
        select(ControlTask).where(
            ControlTask.kind == TaskKind.CONTROL,
            ControlTask.capability == capability,
            ControlTask.status == TaskStatus.QUEUED,
        )
    ).first()
    assert task is not None
    grant = claim_worker_task(
        session,
        worker_id=worker.id,
        protocol_version=PROTOCOL_VERSION,
        capabilities=worker.capabilities,
    )
    assert grant is not None and grant.id == task.id
    digest = request_digest(task)
    start_worker_task(
        session,
        task_id=task.id,
        worker_id=worker.id,
        protocol_version=PROTOCOL_VERSION,
        request_digest_value=digest,
    )
    return complete_worker_task(
        session,
        task_id=task.id,
        worker_id=worker.id,
        protocol_version=PROTOCOL_VERSION,
        request_digest_value=digest,
        result=result,
    )


@pytest.mark.asyncio
async def test_full_file_action_contract_rejects_protects_moves_and_restores(
    contract_session: Session,
) -> None:
    workspace = _workspace(contract_session)
    client_id = uuid4()
    protected = Path(workspace.root_path) / ".env"
    ordinary = Path(workspace.root_path) / "demo.txt"
    protected.write_bytes(b"do-not-touch")
    ordinary.write_bytes(b"stable-demo-content")
    original_digest = hashlib.sha256(ordinary.read_bytes()).hexdigest()

    protected_status = ExternalActionService(contract_session).propose(
        client_id,
        ExternalActionRequest(
            action="file.quarantine.v1", workspace_id=workspace.id, relative_path=".env"
        ),
        "contract-protected-1",
    )
    assert protected_status.status == ActionStatus.DENIED.value
    assert protected.read_bytes() == b"do-not-touch"
    assert contract_session.exec(select(ControlTask)).all() == []

    ordinary_request = ExternalActionRequest(
        action="file.quarantine.v1", workspace_id=workspace.id, relative_path="demo.txt"
    )
    pending = ExternalActionService(contract_session).propose(
        client_id, ordinary_request, "contract-ordinary-1"
    )
    replay = ExternalActionService(contract_session).propose(
        client_id, ordinary_request, "contract-ordinary-1"
    )
    assert pending.id == replay.id
    assert pending.status == replay.status == ActionStatus.PENDING_APPROVAL.value
    assert ordinary.exists()

    approved = await ApprovalService(contract_session).approve(
        pending.id, actor="operator:contract"
    )
    assert approved.status == ActionStatus.APPROVED
    worker = _worker(contract_session)
    quarantine_result = {
        "status": "succeeded",
        "result_kind": "file_quarantine",
        "side_effect": "quarantined",
        "content_sha256": original_digest,
        "size_bytes": len(b"stable-demo-content"),
        "quarantine_entry_id": str(uuid4()),
        "quarantine_relative_path": f"entries/{pending.id.hex}/demo.txt",
    }
    completed = _complete_next_file_task(
        contract_session, worker, "file.quarantine.v1", quarantine_result
    )
    assert completed.status == TaskStatus.SUCCEEDED
    contract_session.expire_all()
    saved = contract_session.get(ToolAction, pending.id)
    assert saved is not None and saved.status == ActionStatus.SUCCEEDED
    assert json.loads(saved.result_json or "{}")["side_effect"] == "quarantined"
    assert contract_session.exec(select(ControlTask)).all()

    entry = QuarantineEntry(
        id=uuid4(),
        workspace_id=workspace.id,
        action_id=pending.id,
        original_relative_path="demo.txt",
        quarantine_relative_path="entries/demo/demo.txt",
        content_sha256=original_digest,
        size_bytes=len(b"stable-demo-content"),
        status="quarantined",
    )
    contract_session.add(entry)
    contract_session.commit()
    restore = ExternalActionService(contract_session).propose(
        client_id,
        ExternalActionRequest(
            action="file.restore.v1", workspace_id=workspace.id, quarantine_entry_id=entry.id
        ),
        "contract-restore-1",
    )
    await ApprovalService(contract_session).approve(restore.id, actor="operator:contract")
    restore_result = {
        "status": "succeeded",
        "result_kind": "file_restore",
        "side_effect": "restored",
        "content_sha256": original_digest,
        "size_bytes": len(b"stable-demo-content"),
    }
    restored_task = _complete_next_file_task(
        contract_session, worker, "file.restore.v1", restore_result
    )
    assert restored_task.status == TaskStatus.SUCCEEDED
    contract_session.expire_all()
    saved_entry = contract_session.get(QuarantineEntry, entry.id)
    saved_restore = contract_session.get(ToolAction, restore.id)
    assert saved_entry is not None and saved_entry.status == "restored"
    assert saved_restore is not None and saved_restore.status == ActionStatus.SUCCEEDED
