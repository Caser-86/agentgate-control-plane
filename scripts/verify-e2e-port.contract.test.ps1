$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$helperPath = Join-Path $PSScriptRoot "e2e-port.ps1"
if (-not (Test-Path -LiteralPath $helperPath)) {
    throw "E2E 端口辅助脚本不存在。"
}
. $helperPath

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
try {
    $occupiedPort = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    $candidate = Get-FreeLoopbackPortRange -StartPort $occupiedPort -Count 3 -SearchLimit 20
    if ($candidate -le $occupiedPort -and $occupiedPort -lt ($candidate + 3)) {
        throw "端口范围分配器返回了已占用端口。"
    }
} finally {
    $listener.Stop()
}

$verifySource = Get-Content -LiteralPath (Join-Path $repoRoot "scripts\verify.ps1") -Raw
if ($verifySource -notmatch "e2e-port\.ps1") {
    throw "verify.ps1 必须使用端口范围分配器。"
}
if ($verifySource -match 'AGENTGATE_E2E_API_PORT\s*=\s*"18000"') {
    throw "verify.ps1 不得占用 Compose 的业务 API 端口。"
}

Write-Output "verify E2E port contract passed"
