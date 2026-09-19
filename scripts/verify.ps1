param(
    [switch]$IncludeWindowsFileContract
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiPython = Join-Path $repoRoot "apps\api\.venv\Scripts\python.exe"
$workerPython = Join-Path $repoRoot "apps\worker\.venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "e2e-port.ps1")

foreach ($contractScript in @(
    "start-local.contract.test.ps1",
    "soak-worker.contract.test.ps1",
    "backup-restore.contract.test.ps1",
    "register-worker.contract.test.ps1",
    "verify-e2e-port.contract.test.ps1"
)) {
    & (Join-Path $PSScriptRoot $contractScript)
    if (-not $?) { throw "脚本契约失败：$contractScript" }
}

Push-Location (Join-Path $repoRoot "apps\api")
try {
    & $apiPython -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    & $apiPython -m mypy app
    if ($LASTEXITCODE -ne 0) { throw "mypy failed." }
    & $apiPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    & $apiPython -m app.evals.runner
    if ($LASTEXITCODE -ne 0) { throw "Deterministic evals failed." }
} finally {
    Pop-Location
}

Push-Location (Join-Path $repoRoot "apps\worker")
try {
    & $workerPython -m ruff check agentgate_worker tests
    if ($LASTEXITCODE -ne 0) { throw "Worker lint failed." }
    & $workerPython -m mypy agentgate_worker
    if ($LASTEXITCODE -ne 0) { throw "Worker typecheck failed." }
    & $workerPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Worker tests failed." }
} finally {
    Pop-Location
}

Push-Location (Join-Path $repoRoot "apps\web")
try {
    npm.cmd run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
    npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed." }
    npm.cmd test -- --run
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    $e2eApiPort = Get-FreeLoopbackPortRange -StartPort 18230 -Count 3
    $e2eWebPort = Get-FreeLoopbackPortRange -StartPort 18300 -Count 3
    $env:AGENTGATE_E2E_API_PORT = [string]$e2eApiPort
    $env:AGENTGATE_E2E_WEB_PORT = [string]$e2eWebPort
    $env:AGENTGATE_E2E_PYTHON = $apiPython
    npm.cmd run test:e2e
    if ($LASTEXITCODE -ne 0) { throw "Browser E2E failed." }
} finally {
    Pop-Location
}

if ($IncludeWindowsFileContract) {
    $contract = Join-Path $repoRoot "scripts\file-action.contract.test.ps1"
    & pwsh -NoProfile -File $contract
    if ($LASTEXITCODE -ne 0) { throw "Windows file-action contract failed." }
}

Write-Host "AgentGate verification passed."
