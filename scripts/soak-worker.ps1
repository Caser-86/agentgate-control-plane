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
    [ValidateRange(1, 10)]
    [int]$MaxGapIntervals = 3,
    [ValidateRange(50, 100)]
    [int]$MinimumCoveragePercent = 95,
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

function ConvertTo-DateTimeOffset {
    param([Parameter(Mandatory = $true)][object]$Value)

    if ($Value -is [DateTimeOffset]) {
        return [DateTimeOffset]$Value
    }
    if ($Value -is [DateTime]) {
        $dateTime = [DateTime]$Value
        if ($dateTime.Kind -eq [DateTimeKind]::Unspecified) {
            $dateTime = [DateTime]::SpecifyKind($dateTime, [DateTimeKind]::Utc)
        }
        return [DateTimeOffset]$dateTime
    }

    $text = [string]$Value
    $parsedOffset = [DateTimeOffset]::MinValue
    if ([DateTimeOffset]::TryParse(
            $text,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AllowWhiteSpaces,
            [ref]$parsedOffset
        )) {
        return $parsedOffset
    }

    $parsedDateTime = [DateTime]::MinValue
    if ([DateTime]::TryParse(
            $text,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind,
            [ref]$parsedDateTime
        )) {
        if ($parsedDateTime.Kind -eq [DateTimeKind]::Unspecified) {
            $parsedDateTime = [DateTime]::SpecifyKind($parsedDateTime, [DateTimeKind]::Utc)
        }
        return [DateTimeOffset]$parsedDateTime
    }

    throw "无法解析探测时间：$text"
}

$startedAt = [DateTimeOffset]::Now
$durationSeconds = $DurationMinutes * 60
$expectedSampleCount = [Math]::Max(1, [Math]::Ceiling($durationSeconds / $IntervalSeconds))
$sampleCount = 0
$failureCount = 0
$consecutiveFailures = 0
$stoppedEarly = $false
$interrupted = $false
$unexpectedError = $null
$maxGapSeconds = 0.0
$lastSampleElapsedSeconds = $null
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Write-SoakLog ("START started_at={0:o} duration_minutes={1} interval_seconds={2} target_id={3}" -f $startedAt, $DurationMinutes, $IntervalSeconds, $TargetId)

try {
    while ($stopwatch.Elapsed.TotalSeconds -lt $durationSeconds) {
        $sampleCount++
        $sampleAt = [DateTimeOffset]::Now
        $sampleElapsedSeconds = $stopwatch.Elapsed.TotalSeconds
        if ($null -ne $lastSampleElapsedSeconds) {
            $maxGapSeconds = [Math]::Max(
                $maxGapSeconds,
                $sampleElapsedSeconds - $lastSampleElapsedSeconds
            )
        }
        $lastSampleElapsedSeconds = $sampleElapsedSeconds
        $ok = $false
        $apiStatus = "error"
        $databaseStatus = "error"
        $queueStatus = "error"
        $workerStatus = "error"
        $targetHealth = "missing"
        $probeStatus = "unknown"
        $probeAgeSeconds = $null
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
                if (-not [string]::IsNullOrWhiteSpace([string]$target.last_probe_at)) {
                    $lastProbeAt = ConvertTo-DateTimeOffset -Value $target.last_probe_at
                    $probeAgeSeconds = [Math]::Max(0, ([DateTimeOffset]::Now - $lastProbeAt).TotalSeconds)
                }
            }
            $probeFresh = $null -ne $probeAgeSeconds -and $null -ne $target -and
                $probeAgeSeconds -le [Math]::Max(90, ([int]$target.interval_seconds * 3))
            $ok = $platform.status -eq "ok" -and
                $apiStatus -eq "ok" -and
                $databaseStatus -eq "ok" -and
                $queueStatus -eq "ok" -and
                $workerStatus -eq "ok" -and
                $targetHealth -eq "healthy" -and
                $probeStatus -eq "healthy" -and
                $probeFresh
            if (-not $ok) {
                $failureReason = if (-not $probeFresh) { "probe_stale_or_missing" } else { "health_check_failed" }
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

        $line = "SAMPLE at={0:o} number={1} elapsed_seconds={2:n1} gap_seconds={3:n1} ok={4} api={5} database={6} queue={7} worker={8} target_health={9} probe={10} probe_age_seconds={11} reason={12}" -f `
            $sampleAt, $sampleCount, $sampleElapsedSeconds, $maxGapSeconds, $ok, $apiStatus, $databaseStatus, $queueStatus, $workerStatus, $targetHealth, $probeStatus, $probeAgeSeconds, $failureReason
        Write-SoakLog $line

        if ($consecutiveFailures -ge $MaxConsecutiveFailures) {
            $stoppedEarly = $true
            break
        }

        $remainingSeconds = [int][Math]::Ceiling($durationSeconds - $stopwatch.Elapsed.TotalSeconds)
        if ($remainingSeconds -gt 0) {
            Start-Sleep -Seconds ([Math]::Min($IntervalSeconds, $remainingSeconds))
        }
    }
} catch {
    $interrupted = $true
    $unexpectedError = $_.Exception.Message
} finally {
    $finishedAt = [DateTimeOffset]::Now
    $coveragePercent = if ($expectedSampleCount -gt 0) {
        [Math]::Round(($sampleCount / $expectedSampleCount) * 100, 2)
    } else { 0 }
    $maxAllowedGapSeconds = $IntervalSeconds * $MaxGapIntervals
    $evidenceSufficient = $coveragePercent -ge $MinimumCoveragePercent -and
        $maxGapSeconds -le $maxAllowedGapSeconds
    $result = if ($interrupted) {
        "INTERRUPTED"
    } elseif ($stoppedEarly) {
        "FAILED_EARLY"
    } elseif ($failureCount -gt 0) {
        "FAILED_WITH_FAILURES"
    } elseif (-not $evidenceSufficient) {
        "INSUFFICIENT_EVIDENCE"
    } else {
        "PASSED"
    }
    Write-SoakLog ("END finished_at={0:o} result={1} samples={2} expected_samples={3} coverage_percent={4} failures={5} consecutive_failures={6} max_gap_seconds={7:n1} max_allowed_gap_seconds={8} unexpected_error={9}" -f `
        $finishedAt, $result, $sampleCount, $expectedSampleCount, $coveragePercent, $failureCount, $consecutiveFailures, $maxGapSeconds, $maxAllowedGapSeconds, $unexpectedError)
}

if ($interrupted) {
    exit 3
}
if ($stoppedEarly -or $failureCount -gt 0 -or -not $evidenceSufficient) {
    exit 2
}
exit 0
