param(
    [ValidateSet("mock", "openai_compatible")]
    [string]$Provider = "mock"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$env:AGENTGATE_LLM_PROVIDER = $Provider

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required for the Compose foundation."
}

function Get-ComposeLoopbackPort([object]$service, [int]$target) {
    $matches = @($service.ports | Where-Object { [int]$_.target -eq $target })
    if ($matches.Count -ne 1 -or $matches[0].host_ip -ne "127.0.0.1") {
        throw "Service port $target must have exactly one 127.0.0.1 binding."
    }
    return [int]$matches[0].published
}

# Compose resolves AGENTGATE_API_PORT and AGENTGATE_WEB_PORT from the environment.
$configJson = docker compose config --format json
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }
$config = $configJson | ConvertFrom-Json
$apiPort = Get-ComposeLoopbackPort $config.services.api 8000
$webPort = Get-ComposeLoopbackPort $config.services.web 80

Write-Host "Starting PostgreSQL for the local migration prerequisite..."
docker compose up -d postgres
$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    docker compose exec -T postgres pg_isready -U agentgate -d agentgate 2>$null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw "PostgreSQL did not become ready within 60 seconds." }

& (Join-Path $PSScriptRoot "migrate-local.ps1")
if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }

Write-Host "Starting API, scheduler, control-worker and web..."
docker compose up -d --build api scheduler control-worker web
$deadline = (Get-Date).AddSeconds(60)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/health" -TimeoutSec 2
        if ($response.status -eq "ok") { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $healthy) { throw "AgentGate API did not become healthy within 60 seconds." }
Write-Host "AgentGate foundation is ready at http://127.0.0.1:$webPort (provider: $Provider)."
Write-Host "Frontend development commands must use npm.cmd on Windows."
