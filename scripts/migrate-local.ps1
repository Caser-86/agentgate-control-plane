$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
docker compose run --rm api python -c "from app.config import get_settings; from app.db import upgrade_to_head; upgrade_to_head(get_settings().database_url)"
if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
Write-Host "Database migration completed."
