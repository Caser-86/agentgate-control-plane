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

Push-Location (Join-Path $repoRoot "apps\web")
try {
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed." }
    npm test -- --run
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    $env:AGENTGATE_E2E_API_PORT = "18000"
    $env:AGENTGATE_E2E_PYTHON = $apiPython
    npm run test:e2e
    if ($LASTEXITCODE -ne 0) { throw "Browser E2E failed." }
} finally {
    Pop-Location
}

Write-Host "AgentGate verification passed."
