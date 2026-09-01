$scriptPath = Join-Path $PSScriptRoot "verify-foundation.ps1"
$source = Get-Content -Raw -LiteralPath $scriptPath

if ($source -notmatch '\$maxWorkerAttempts\s*=\s*\d+') {
    throw "Foundation verification must define a bounded worker attempt count."
}
if ($source -notmatch '(?s)for\s*\([^)]*\$maxWorkerAttempts[^)]*\).*?start-worker\.ps1') {
    throw "Foundation verification must invoke one-shot start-worker inside a bounded retry loop."
}
if ($source -notmatch '(?s)for\s*\([^)]*\$maxWorkerAttempts[^)]*\).*?api/v1/checks/\$\(\$check\.id\)') {
    throw "Foundation verification must read the submitted task status on each attempt."
}
if ($source -notmatch 'status.*queued|queued.*status') {
    throw "Foundation verification must explicitly handle queued task status."
}
if ($source -notmatch '(?s)status.*failed.*throw|throw.*status.*failed') {
    throw "Foundation verification must fail clearly when the submitted task fails."
}
if ($source -notmatch '(?s)maxWorkerAttempts.*throw|throw.*maxWorkerAttempts') {
    throw "Foundation verification must fail clearly after exhausting worker attempts."
}

Write-Output "verify-foundation contract checks passed"
