$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required to stop the Compose foundation."
}
docker compose down
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed." }
Write-Host "AgentGate local services stopped; the PostgreSQL volume was preserved."
