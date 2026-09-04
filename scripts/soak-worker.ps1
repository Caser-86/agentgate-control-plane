[CmdletBinding()]
param(
    [string]$ApiUrl = "http://127.0.0.1:18230",
    [Parameter(Mandatory = $true)]
    [string]$TargetId,
    [ValidateRange(1, 10080)]
    [int]$DurationMinutes = 1440,
    [ValidateRange(5, 3600)]
    [int]$IntervalSeconds = 30,
    [ValidateRange(1, 10)]
    [int]$MaxConsecutiveFailures = 3,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$parsedApiUrl = $null
if (-not [Uri]::TryCreate($ApiUrl, [UriKind]::Absolute, [ref]$parsedApiUrl) -or
    $parsedApiUrl.Scheme -notin @("http", "https") -or
    [string]::IsNullOrWhiteSpace($parsedApiUrl.DnsSafeHost) -or
    $parsedApiUrl.UserInfo -or
    $parsedApiUrl.Query -or
    $parsedApiUrl.Fragment -or
    $parsedApiUrl.AbsolutePath -notin @("", "/")) {
    throw "API URL must be a valid loopback HTTP(S) URL."
}
$loopbackHost = $parsedApiUrl.DnsSafeHost.ToLowerInvariant().TrimEnd('.')
if ($loopbackHost -notin @("localhost", "127.0.0.1", "::1")) {
    throw "Remote API targets are not supported; use a local loopback API URL."
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))) "data\worker-soak.log"
} else {
    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
}
$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

function Write-SoakLog {
    param([string]$Line)
    Add-Content -LiteralPath $OutputPath -Value $Line -Encoding UTF8
    Write-Output $Line
}

$startedAt = Get-Date
$deadline = $startedAt.AddMinutes($DurationMinutes)
$sampleCount = 0
$failureCount = 0
$consecutiveFailures = 0
$stoppedEarly = $false

Write-SoakLog ("START started_at={0:o} duration_minutes={1} interval_seconds={2} target_id={3}" -f $startedAt, $DurationMinutes, $IntervalSeconds, $TargetId)

try {
    while ((Get-Date) -lt $deadline) {
        $sampleCount++
        $sampleAt = Get-Date
        $ok = $false
        $apiStatus = "error"
        $databaseStatus = "error"
        $queueStatus = "error"
        $workerStatus = "error"
        $targetHealth = "missing"
        $probeStatus = "unknown"
        $failureReason = ""

        try {
            $platform = Invoke-RestMethod -Method Get -Uri "$ApiUrl/api/platform/health" -TimeoutSec 10
            $apiStatus = [string]$platform.checks.api.status
            $databaseStatus = [string]$platform.checks.database.status
            $queueStatus = [string]$platform.checks.queue.status
            $workerStatus = [string]$platform.checks.worker.status
            $targets = Invoke-RestMethod -Method Get -Uri "$ApiUrl/api/monitor/targets" -TimeoutSec 10
            $target = $targets | Where-Object { [string]$_.id -eq $TargetId } | Select-Object -First 1
            if ($null -ne $target) {
                $targetHealth = [string]$target.health
                $probeStatus = [string]$target.last_probe_status
            }
            $ok = $platform.status -eq "ok" -and
                $apiStatus -eq "ok" -and
                $databaseStatus -eq "ok" -and
                $queueStatus -eq "ok" -and
                $workerStatus -eq "ok" -and
                $targetHealth -eq "healthy" -and
                $probeStatus -eq "healthy"
            if (-not $ok) {
                $failureReason = "health_check_failed"
            }
        } catch {
            $failureReason = "request_failed"
        }

        if ($ok) {
            $consecutiveFailures = 0
        } else {
            $failureCount++
            $consecutiveFailures++
        }

        $line = "SAMPLE at={0:o} number={1} ok={2} api={3} database={4} queue={5} worker={6} target_health={7} probe={8} reason={9}" -f `
            $sampleAt, $sampleCount, $ok, $apiStatus, $databaseStatus, $queueStatus, $workerStatus, $targetHealth, $probeStatus, $failureReason
        Write-SoakLog $line

        if ($consecutiveFailures -ge $MaxConsecutiveFailures) {
            $stoppedEarly = $true
            break
        }

        $remainingSeconds = [int][Math]::Ceiling(($deadline - (Get-Date)).TotalSeconds)
        if ($remainingSeconds -gt 0) {
            Start-Sleep -Seconds ([Math]::Min($IntervalSeconds, $remainingSeconds))
        }
    }
} finally {
    $finishedAt = Get-Date
    $result = if ($stoppedEarly) { "FAILED_EARLY" } elseif ($failureCount -eq 0) { "PASSED" } else { "COMPLETED_WITH_TRANSIENT_FAILURES" }
    Write-SoakLog ("END finished_at={0:o} result={1} samples={2} failures={3} consecutive_failures={4}" -f `
        $finishedAt, $result, $sampleCount, $failureCount, $consecutiveFailures)
}

if ($stoppedEarly) {
    exit 2
}
exit 0
