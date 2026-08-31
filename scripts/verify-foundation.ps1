param([int]$MaxHeartbeatAgeSeconds = 90)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$config = docker compose config
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }
$postgresBlock = ($config -split '(?m)^  api:')[0]
if ($postgresBlock -match '(?m)^    ports:') { throw "PostgreSQL must not publish a host port." }
if ($config -notmatch '127\.0\.0\.1:.*8000:8000') { throw "API is not loopback-only." }
if ($config -notmatch '127\.0\.0\.1:.*5173:80') { throw "Web is not loopback-only." }

$health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
if ($health.status -ne "ok") { throw "API health check failed." }
$auth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/status" -TimeoutSec 5
if ($null -eq $auth.setup_required) { throw "Authentication status check failed." }
$platform = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/platform/self-check" -TimeoutSec 5
if ([string]::IsNullOrWhiteSpace([string]$platform.migration_head) -or $platform.migration_head -eq "unknown") { throw "Migration head is missing." }
if ($platform.stale_lease_count -gt 0) { throw "A stale queue lease requires scheduler cleanup." }
if ($null -eq $platform.worker_heartbeat_age_seconds -or $platform.worker_heartbeat_age_seconds -gt $MaxHeartbeatAgeSeconds) { throw "Worker heartbeat is missing or stale." }
if ($platform.PSObject.Properties.Name -contains "api_key") { throw "Self-check exposed a secret field." }
Write-Host "Foundation verification passed: localhost bindings, migration, auth, heartbeat and self-check."
