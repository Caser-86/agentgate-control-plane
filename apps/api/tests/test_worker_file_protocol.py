from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.control.enums import TaskKind
from app.control.models import ControlTask
from app.schemas_worker_files import FileInspectTask
from app.services.worker_protocol import (
    FILE_CAPABILITIES,
    _task_is_safe,
    sanitize_file_result,
)


def test_file_task_rejects_absolute_path_and_unknown_field() -> None:
    with pytest.raises(ValidationError):
        FileInspectTask.model_validate(
            {
                "action_id": str(uuid4()),
                "workspace_id": str(uuid4()),
                "workspace_version": 1,
                "relative_path": r"C:\secret.txt",
                "arguments_digest": "a" * 64,
                "policy_version": "file-policy.v1",
                "worker_root": r"C:\root",
            }
        )


def test_file_capabilities_are_strictly_allowlisted() -> None:
    assert FILE_CAPABILITIES == frozenset(
        {"file.inspect.v1", "file.quarantine.v1", "file.restore.v1"}
    )


def test_file_task_is_safe_only_when_capability_matches_schema() -> None:
    task = ControlTask(
        kind=TaskKind.CONTROL,
        capability="file.inspect.v1",
        payload={
            "action_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "workspace_version": 1,
            "relative_path": "notes.txt",
            "arguments_digest": "a" * 64,
            "policy_version": "file-policy.v1",
        },
        idempotency_key="file-safe-task",
    )
    assert _task_is_safe(task) is True
    task.payload["root_path"] = r"C:\secret"
    assert _task_is_safe(task) is False


def test_file_result_sanitizer_keeps_digest_and_drops_unknown_content() -> None:
    result = sanitize_file_result(
        {
            "status": "succeeded",
            "result_kind": "file_metadata",
            "side_effect": "none",
            "content_sha256": "b" * 64,
            "size_bytes": 12,
            "content": "must never be stored",
        }
    )

    assert result == {
        "status": "succeeded",
        "result_kind": "file_metadata",
        "side_effect": "none",
        "content_sha256": "b" * 64,
        "size_bytes": 12,
    }
