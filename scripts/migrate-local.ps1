$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
docker compose run --rm --build migrate
if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
Write-Host "Database migration completed."
