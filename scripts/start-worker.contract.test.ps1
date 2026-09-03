$worker = Join-Path $PSScriptRoot "start-worker.ps1"
$workerSource = Get-Content -Raw -LiteralPath $worker
$paramBlock = [regex]::Match($workerSource, '(?s)\bparam\s*\((.*?)\n\)')
if (-not $paramBlock.Success -or $paramBlock.Groups[1].Value -match '\$env:AGENTGATE_WORKER_ENROLLMENT_TOKEN') {
    throw "Enrollment token environment variable must not be read in the parameter default block."
}
$validationEnd = $workerSource.IndexOf('if ($ApiPort -lt 1 -or $ApiPort -gt 65535)')
$validationEnd = $workerSource.IndexOf("`n", $validationEnd)
$tokenRead = $workerSource.IndexOf('$env:AGENTGATE_WORKER_ENROLLMENT_TOKEN')
if ($tokenRead -lt 0 -or $validationEnd -lt 0 -or $tokenRead -lt $validationEnd) {
    throw "Enrollment token environment variable must be read after API validation."
}
$conflict = & pwsh -NoProfile -File $worker -ApiUrl "http://127.0.0.1:18000" -ApiPort 18001 2>&1
if ($LASTEXITCODE -eq 0 -or ($conflict -join "`n") -notmatch "conflicts with explicit ApiPort") { throw "Conflicting ApiUrl/ApiPort was not rejected." }
$remote = & pwsh -NoProfile -File $worker -ApiUrl "https://example.com:18000" 2>&1
if ($LASTEXITCODE -eq 0 -or ($remote -join "`n") -notmatch "Remote API targets are not supported") { throw "Remote API URL was not rejected." }
$matching = & pwsh -NoProfile -File $worker -ApiUrl "http://127.0.0.1:18000" -ApiPort 18000 2>&1
if ($LASTEXITCODE -eq 0 -or ($matching -join "`n") -notmatch "one-time worker enrollment token is required") { throw "Matching ApiUrl/ApiPort did not proceed to worker startup with a failure exit code." }
Write-Output "start-worker contract checks passed"
