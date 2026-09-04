from pathlib import Path
from uuid import uuid4

import pytest

from app.files.models import ManagedWorkspace
from app.models import RiskLevel
from app.services.file_actions import ActionCaller, FileActionPolicy


@pytest.fixture
def workspace(tmp_path: Path) -> ManagedWorkspace:
    return ManagedWorkspace(
        id=uuid4(),
        name="演示工作区",
        root_path=str(tmp_path),
        canonical_root_path=str(tmp_path),
        quarantine_root_path=str(tmp_path.parent / "quarantine"),
        protected_patterns=[".git/**", ".env", "protected/**"],
        enabled=True,
        version=3,
    )


@pytest.fixture
def caller() -> ActionCaller:
    return ActionCaller(client_id=uuid4())


def test_inspect_is_auto_allowed_for_regular_unprotected_path(
    workspace: ManagedWorkspace, caller: ActionCaller
) -> None:
    decision = FileActionPolicy().evaluate(
        "file.inspect.v1", workspace, {"relative_path": "notes/a.txt"}, caller
    )

    assert decision.decision == "allow_auto"
    assert decision.risk_level is RiskLevel.LOW
    assert decision.requires_approval is False


def test_quarantine_protected_path_is_denied_without_approval(
    workspace: ManagedWorkspace, caller: ActionCaller
) -> None:
    decision = FileActionPolicy().evaluate(
        "file.quarantine.v1", workspace, {"relative_path": ".env"}, caller
    )

    assert decision.decision == "deny"
    assert decision.code == "protected_path"
    assert decision.requires_approval is False


def test_quarantine_unprotected_path_requires_approval(
    workspace: ManagedWorkspace, caller: ActionCaller
) -> None:
    decision = FileActionPolicy().evaluate(
        "file.quarantine.v1", workspace, {"relative_path": "notes/a.txt"}, caller
    )

    assert decision.decision == "require_approval"
    assert decision.risk_level is RiskLevel.MEDIUM
    assert decision.requires_approval is True


def test_invalid_relative_path_is_denied_with_stable_code(
    workspace: ManagedWorkspace, caller: ActionCaller
) -> None:
    decision = FileActionPolicy().evaluate(
        "file.inspect.v1", workspace, {"relative_path": r"C:\secret.txt"}, caller
    )

    assert decision.decision == "deny"
    assert decision.code == "invalid_relative_path"
