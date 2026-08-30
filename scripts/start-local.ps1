param(
    [ValidateSet("mock", "openai_compatible")]
    [string]$Provider = "mock"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\api"
$webRoot = Join-Path $repoRoot "apps\web"
$stateRoot = Join-Path $repoRoot ".agentgate"
$apiPidPath = Join-Path $stateRoot "api.pid"
$webPidPath = Join-Path $stateRoot "web.pid"

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    $examplePath = Join-Path $repoRoot ".env.example"
    if (-not (Test-Path -LiteralPath $examplePath)) {
        throw "Neither .env nor .env.example exists."
    }
    Copy-Item -LiteralPath $examplePath -Destination (Join-Path $repoRoot ".env")
    Write-Host "Created .env from .env.example. Set a newly rotated key before using live mode."
}

if ((Test-Path -LiteralPath $apiPidPath) -or (Test-Path -LiteralPath $webPidPath)) {
    throw "AgentGate PID files already exist. Run scripts/stop-local.ps1 first."
}

New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $apiRoot "data") | Out-Null

$pythonPath = Join-Path $apiRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
}
$nodePath = (Get-Command node -ErrorAction Stop).Source
$vitePath = Join-Path $webRoot "node_modules\vite\bin\vite.js"
if (-not (Test-Path -LiteralPath $vitePath)) {
    throw "Vite is not installed. Run npm ci in apps/web first."
}

$env:AGENTGATE_LLM_PROVIDER = $Provider
$env:AGENTGATE_DATABASE_URL = "sqlite:///./data/agentgate.db"
$env:AGENTGATE_WEB_ORIGIN = "http://localhost:5173"

$apiArguments = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir `"$apiRoot`""
$webArguments = "`"$vitePath`" --host localhost --port 5173"
$apiProcess = Start-Process -FilePath $pythonPath -ArgumentList $apiArguments -WorkingDirectory $apiRoot -WindowStyle Hidden -PassThru
$webProcess = Start-Process -FilePath $nodePath -ArgumentList $webArguments -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru

Set-Content -LiteralPath $apiPidPath -Value $apiProcess.Id -NoNewline
Set-Content -LiteralPath $webPidPath -Value $webProcess.Id -NoNewline

$deadline = (Get-Date).AddSeconds(30)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $ready) {
    Write-Error "AgentGate API did not become healthy within 30 seconds."
    exit 1
}

Write-Host "AgentGate is ready at http://localhost:5173 (provider: $Provider)"
