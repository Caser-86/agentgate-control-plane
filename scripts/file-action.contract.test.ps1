param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot "apps\api\.venv\Scripts\python.exe"
$workerRoot = Join-Path $repoRoot "apps\worker"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "找不到用于执行 Worker 合约测试的 Python：$python"
}

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$contractRoot = Join-Path $tempRoot ("agentgate-file-contract-" + [guid]::NewGuid().ToString("N"))
$resolvedContractRoot = [IO.Path]::GetFullPath($contractRoot)
$env:PYTHONPATH = $workerRoot

$pythonCode = @'
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

from agentgate_worker.client import WorkspaceContext
from agentgate_worker.filesystem import FileActionError
from agentgate_worker.quarantine import QuarantineService

root = Path(sys.argv[1]) / "workspace"
quarantine = Path(sys.argv[1]) / "quarantine"
root.mkdir(parents=True)
quarantine.mkdir(parents=True)
context = WorkspaceContext(
    workspace_id=str(uuid4()),
    version=1,
    root_path=str(root),
    quarantine_root_path=str(quarantine),
    protected_patterns=(".env", "protected/**"),
)
service = QuarantineService(Path(sys.argv[1]) / "file-actions.jsonl")

protected = root / ".env"
protected.write_text("must remain", encoding="utf-8")
try:
    service.quarantine(context, uuid4(), ".env")
except FileActionError as error:
    assert error.code == "protected_path"
else:
    raise AssertionError("protected path was not denied")
assert protected.exists()

original = root / "demo.txt"
original.write_bytes(b"contract-data")
expected_digest = hashlib.sha256(original.read_bytes()).hexdigest()
action_id = uuid4()
first = service.quarantine(context, action_id, "demo.txt")
second = service.quarantine(context, action_id, "demo.txt")
assert first.status == second.status == "quarantined"
assert first.content_sha256 == expected_digest == second.content_sha256
assert not original.exists()
assert Path(first.entry.quarantine_absolute_path).exists()

restored = service.restore(context, first.entry)
assert restored.status == "restored"
assert original.exists()
assert hashlib.sha256(original.read_bytes()).hexdigest() == expected_digest

original.write_bytes(b"user-created-content")
conflict = service.restore(context, first.entry)
assert conflict.status == "destination_conflict"
assert original.read_bytes() == b"user-created-content"
print("文件动作 Windows 合约测试通过：保护文件未动、隔离真实移动、重复提交幂等、恢复不覆盖")
'@

try {
    New-Item -ItemType Directory -Path $resolvedContractRoot -Force | Out-Null
    & $python -c $pythonCode $resolvedContractRoot
    if ($LASTEXITCODE -ne 0) {
        throw "文件动作合约测试失败。"
    }
} finally {
    $tempPrefix = $tempRoot.TrimEnd("\")
    if ($resolvedContractRoot.StartsWith("$tempPrefix\agentgate-file-contract-", [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $resolvedContractRoot) {
            Remove-Item -LiteralPath $resolvedContractRoot -Recurse -Force
        }
    } else {
        throw "拒绝清理未确认的合约测试目录：$resolvedContractRoot"
    }
}
