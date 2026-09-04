param(
    [switch]$IncludeWindowsFileContract
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiPython = Join-Path $repoRoot "apps\api\.venv\Scripts\python.exe"

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
    & $apiPython -m ruff check agentgate_worker tests
    if ($LASTEXITCODE -ne 0) { throw "Worker lint failed." }
    & $apiPython -m mypy agentgate_worker
    if ($LASTEXITCODE -ne 0) { throw "Worker typecheck failed." }
    & $apiPython -m pytest -q
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
    $env:AGENTGATE_E2E_API_PORT = "18000"
    $env:AGENTGATE_E2E_WEB_PORT = "18100"
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
