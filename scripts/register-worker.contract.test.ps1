$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "register-worker.ps1"
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "register-worker.ps1 不存在。"
}
$source = Get-Content -LiteralPath $scriptPath -Raw

foreach ($required in @(
    "/api/auth/tokens",
    "worker:enroll",
    "AGENTGATE_WORKER_ENROLLMENT_TOKEN",
    "-Environment",
    "-WindowStyle Hidden",
    "credentials.bin",
    "AGENTGATE_SESSION_COOKIE",
    "AGENTGATE_CSRF_TOKEN"
)) {
    if ($source -notmatch [regex]::Escape($required)) {
        throw "register-worker.ps1 缺少安全注册契约：$required"
    }
}

if ($source -notmatch "workerArgumentLine" -or $source -notmatch "Replace") {
    throw "register-worker.ps1 必须正确引用含空格的 PowerShell 参数。"
}
foreach ($marker in @("registrationArguments", "registrationProcess", "-Wait", "workerArguments")) {
    if ($source -notmatch [regex]::Escape($marker)) {
        throw "register-worker.ps1 必须将一次性注册与持续运行分离：$marker"
    }
}

if ($source -match '(?i)Write-(Host|Output).*enrollment\.token') {
    throw "register-worker.ps1 不得打印注册令牌。"
}
if ($source -notmatch 'Start-Process') {
    throw "register-worker.ps1 必须使用独立 Worker 进程。"
}

Write-Output "register-worker contract checks passed"
