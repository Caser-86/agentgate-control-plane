param(
    [int]$MaxHeartbeatAgeSeconds = 90,
    [string]$OperatorSessionCookie = $env:AGENTGATE_SESSION_COOKIE,
    [string]$WorkerEnrollmentToken = $env:AGENTGATE_WORKER_ENROLLMENT_TOKEN,
    [string]$WorkerCheckToken = $env:AGENTGATE_WORKER_CHECK_TOKEN
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
# Compose resolves AGENTGATE_API_PORT and AGENTGATE_WEB_PORT from the environment.
$configJson = docker compose config --format json
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }
$config = $configJson | ConvertFrom-Json
if ($null -eq $config.services.postgres.ports) { }
elseif (@($config.services.postgres.ports).Count -gt 0) { throw "PostgreSQL must not publish a host port." }

function Get-LoopbackPort([object]$service, [int]$target) {
    $matches = @($service.ports | Where-Object { [int]$_.target -eq $target })
    if ($matches.Count -ne 1 -or $matches[0].host_ip -ne "127.0.0.1") {
        throw "Service port $target must have exactly one 127.0.0.1 binding."
    }
    return [int]$matches[0].published
}

$apiPort = Get-LoopbackPort $config.services.api 8000
$webPort = Get-LoopbackPort $config.services.web 80

$health = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/health" -TimeoutSec 5
if ($health.status -ne "ok") { throw "API health check failed." }
$auth = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/auth/status" -TimeoutSec 5
if ($null -eq $auth.setup_required) { throw "Authentication status check failed." }
$operatorHeaders = @{}
if ([string]::IsNullOrWhiteSpace($OperatorSessionCookie)) {
    throw "Authenticated platform self-check requires AGENTGATE_SESSION_COOKIE; cookie contents are never printed."
}
$operatorHeaders["Cookie"] = "agentgate_session=$OperatorSessionCookie"

if ([string]::IsNullOrWhiteSpace($WorkerCheckToken) -or [string]::IsNullOrWhiteSpace($WorkerEnrollmentToken)) {
    throw "Worker self-check requires AGENTGATE_WORKER_CHECK_TOKEN and AGENTGATE_WORKER_ENROLLMENT_TOKEN; token contents are never printed."
}
$readiness = Invoke-RestMethod -Headers $operatorHeaders -Uri ("http://127.0.0.1:$apiPort/api/platform/" + "self-check") -TimeoutSec 5
if ($null -eq $readiness.migration_check -or $readiness.migration_check.status -ne "ok" -or $readiness.migration_check.code -ne "database_migration_current") {
    throw "Database migration is missing or stale before native Worker execution."
}
$workerRoot = Join-Path $repoRoot "apps\worker"
$workerVenv = Join-Path $workerRoot ".venv"
$workerPython = Join-Path $workerVenv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $workerPython)) { throw "Native Worker Python runtime was not found." }
$workerImportCheck = & $workerPython -c "import win32crypt; import agentgate_worker; print('worker-runtime-ok')" 2>&1
if ($LASTEXITCODE -ne 0 -or ($workerImportCheck -join "") -notmatch "worker-runtime-ok") {
    throw "Native Worker dependencies are not installed in apps/worker/.venv; run .\scripts\setup-local.ps1 (the command is idempotent and does not print secrets)."
}
$check = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$apiPort/api/v1/checks" `
    -Headers @{ Authorization = "Bearer $WorkerCheckToken" } `
    -ContentType "application/json" `
    -Body (@{ check_type = "platform.self_check"; target = "local"; parameters = @{}; idempotency_key = "verify-foundation:$([Guid]::NewGuid())" } | ConvertTo-Json -Compress)
if ($null -eq $check.id) { throw "Foundation self-check did not return a task id." }
$workerStateDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agentgate-worker-verify-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $workerStateDir -Force | Out-Null
try {
    & (Join-Path $repoRoot "scripts\start-worker.ps1") `
        -ApiUrl "http://127.0.0.1:$apiPort" `
        -StateDir $workerStateDir `
        -EnrollmentToken $WorkerEnrollmentToken
    if ($LASTEXITCODE -ne 0) { throw "Native Worker self-check round trip failed." }
} finally {
    if (Test-Path -LiteralPath $workerStateDir) {
        Remove-Item -LiteralPath (Join-Path $workerStateDir "credentials.bin") -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $workerStateDir "journal.db") -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $workerStateDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
$checkStatus = $null
try {
    $checkStatus = Invoke-RestMethod -Headers @{ Authorization = "Bearer $WorkerCheckToken" } -Uri "http://127.0.0.1:$apiPort/api/v1/checks/$($check.id)" -TimeoutSec 5
} catch {
    throw "Submitted foundation self-check status could not be read."
}
if ($null -eq $checkStatus -or "$($checkStatus.id)" -ne "$($check.id)") { throw "Submitted foundation self-check task was not found." }
if ($checkStatus.status -ne "succeeded" -or $null -eq $checkStatus.result) { throw "Submitted foundation self-check did not reach succeeded." }
$allowedResultKeys = @("status", "detail", "worker_version", "protocol_version", "capabilities")
$resultKeys = @($checkStatus.result.PSObject.Properties.Name)
if ($checkStatus.result.status -ne "succeeded" -or @($resultKeys | Where-Object { $_ -notin $allowedResultKeys }).Count -gt 0) {
    throw "Submitted foundation self-check returned an invalid result."
}
$platform = Invoke-RestMethod -Headers $operatorHeaders -Uri "http://127.0.0.1:$apiPort/api/platform/self-check" -TimeoutSec 5
if ($null -eq $platform.migration_check -or $platform.migration_check.status -ne "ok" -or $platform.migration_check.code -ne "database_migration_current") { throw "Database migration is missing or stale." }
if ($platform.stale_lease_count -gt 0) { throw "A stale queue lease requires scheduler cleanup." }
if ($null -eq $platform.worker_heartbeat_age_seconds -or $platform.worker_heartbeat_age_seconds -gt $MaxHeartbeatAgeSeconds) { throw "Worker heartbeat is missing or stale." }
if ($platform.PSObject.Properties.Name -contains "api_key") { throw "Self-check exposed a secret field." }
Write-Host "Foundation verification passed: loopback ports $apiPort/$webPort, migration, auth, heartbeat and native Worker self-check."
