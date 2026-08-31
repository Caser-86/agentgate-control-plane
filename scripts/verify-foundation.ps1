param([int]$MaxHeartbeatAgeSeconds = 90)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$config = docker compose config | Out-String
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }
function Get-ComposeServiceBlock([string]$Text, [string]$Service) {
    $match = [regex]::Match($Text, "(?ms)^  ${Service}:\r?\n(?:(?!^  [a-z0-9-]+:\r?$).)*")
    if (-not $match.Success) { throw "Compose service '$Service' is missing." }
    return $match.Value
}

$postgresBlock = Get-ComposeServiceBlock $config "postgres"
if ($postgresBlock -match '(?m)^\s+ports:\s*$') { throw "PostgreSQL must not publish a host port." }

function Assert-LoopbackPort([string]$Service, [string]$Block, [string]$Published, [string]$Target) {
    if ($Block -notmatch '(?m)^\s+ports:\s*$') { throw "$Service has no published loopback port." }
    if ($Block -notmatch '(?m)^\s+host_ip:\s+127\.0\.0\.1\s*$') { throw "$Service is not loopback-only." }
    if ($Block -notmatch "(?m)^\s+published:\s+`"?$Published`"?\s*$") { throw "$Service published port is unsafe." }
    if ($Block -notmatch "(?m)^\s+target:\s+$Target\s*$") { throw "$Service target port is incorrect." }
}

Assert-LoopbackPort "API" (Get-ComposeServiceBlock $config "api") "8000" "8000"
Assert-LoopbackPort "Web" (Get-ComposeServiceBlock $config "web") "5173" "80"

$health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
if ($health.status -ne "ok") { throw "API health check failed." }
$auth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/status" -TimeoutSec 5
if ($null -eq $auth.setup_required) { throw "Authentication status check failed." }
$platform = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/platform/self-check" -TimeoutSec 5
if ($null -eq $platform.migration_check -or $platform.migration_check.status -ne "ok" -or $platform.migration_check.code -ne "database_migration_current") { throw "Database migration is missing or stale." }
if ($platform.stale_lease_count -gt 0) { throw "A stale queue lease requires scheduler cleanup." }
if ($null -eq $platform.worker_heartbeat_age_seconds -or $platform.worker_heartbeat_age_seconds -gt $MaxHeartbeatAgeSeconds) { throw "Worker heartbeat is missing or stale." }
if ($platform.PSObject.Properties.Name -contains "api_key") { throw "Self-check exposed a secret field." }
Write-Host "Foundation verification passed: localhost bindings, migration, auth, heartbeat and self-check."
