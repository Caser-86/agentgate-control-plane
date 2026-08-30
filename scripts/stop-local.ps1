$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$stateRoot = Join-Path $repoRoot ".agentgate"

foreach ($pidPath in @(
    (Join-Path $stateRoot "api.pid"),
    (Join-Path $stateRoot "web.pid")
)) {
    if (-not (Test-Path -LiteralPath $pidPath)) {
        continue
    }

    $rawPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        Write-Warning "Ignoring malformed PID file $pidPath."
        continue
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Remove-Item -LiteralPath $pidPath -Force
        continue
    }

    $commandLine = [string](Get-CimInstance Win32_Process -Filter "ProcessId = $processId").CommandLine
    if (-not $commandLine.Contains($repoRoot)) {
        Write-Warning "PID $processId does not belong to this AgentGate checkout; leaving it running."
        continue
    }

    Stop-Process -Id $processId -Force
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "Stopped AgentGate process $processId."
}
