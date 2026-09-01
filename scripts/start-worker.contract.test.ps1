$worker = Join-Path $PSScriptRoot "start-worker.ps1"
$conflict = & pwsh -NoProfile -File $worker -ApiUrl "http://127.0.0.1:18000" -ApiPort 18001 2>&1
if ($LASTEXITCODE -eq 0 -or ($conflict -join "`n") -notmatch "conflicts with explicit ApiPort") { throw "Conflicting ApiUrl/ApiPort was not rejected." }
$remote = & pwsh -NoProfile -File $worker -ApiUrl "https://example.com:18000" 2>&1
if ($LASTEXITCODE -eq 0 -or ($remote -join "`n") -notmatch "Remote API targets are not supported") { throw "Remote API URL was not rejected." }
$matching = & pwsh -NoProfile -File $worker -ApiUrl "http://127.0.0.1:18000" -ApiPort 18000 2>&1
if (($matching -join "`n") -notmatch "one-time worker enrollment token is required") { throw "Matching ApiUrl/ApiPort did not proceed to worker startup." }
Write-Output "start-worker contract checks passed"
