$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "soak-worker.ps1"
$source = Get-Content -Raw -LiteralPath $scriptPath

foreach ($parameter in @("MinimumCoveragePercent", "MaxGapIntervals")) {
    $variableName = '$' + $parameter
    if ($source -notmatch [regex]::Escape($variableName)) {
        throw "稳定性脚本缺少参数：$parameter"
    }
}
foreach ($marker in @("INTERRUPTED", "INSUFFICIENT_EVIDENCE", "probe_stale_or_missing")) {
    if ($source -notmatch [regex]::Escape($marker)) {
        throw "稳定性脚本缺少证据状态：$marker"
    }
}
foreach ($marker in @("ConvertTo-DateTimeOffset", "DateTimeKind]::Utc", "RoundtripKind")) {
    if ($source -notmatch [regex]::Escape($marker)) {
        throw "稳定性脚本缺少 UTC 时间解析边界：$marker"
    }
}
if ($source -notmatch '\[Math\]::Ceiling\(\$durationSeconds\s*/\s*\$IntervalSeconds\)') {
    throw "稳定性脚本必须按可完成采样周期计算预期覆盖率。"
}
if ($source -notmatch '(?s)if \(\$interrupted\).*?exit 3') {
    throw "手工中断或环境异常必须使用退出码 3。"
}
if ($source -notmatch '(?s)\$stoppedEarly.*?exit 2') {
    throw "业务失败或证据不足必须使用退出码 2。"
}
if ($source -notmatch '\[System\.Diagnostics\.Stopwatch\]::StartNew\(\)') {
    throw "稳定性间隔必须使用单调时钟。"
}

Write-Output "soak-worker contract checks passed"
