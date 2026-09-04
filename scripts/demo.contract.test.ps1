$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot "demo.ps1"
$source = Get-Content -Raw -LiteralPath $scriptPath
$readme = Get-Content -Raw -LiteralPath (Join-Path $repoRoot "README.md")

foreach ($required in @(
    "[int]`$ApiPort",
    "[int]`$WebPort",
    "[switch]`$ResetDemoData",
    "[switch]`$NoBrowser",
    "AGENTGATE_WORKSPACE_ALLOWED_ROOT",
    "AGENTGATE_SESSION_COOKIE",
    "Native Worker",
    "dedicatedWorkerRunning",
    "workerArgumentLine",
    "ArgumentList `$workerArgumentLine",
    "不改写 .env",
    "文件治理数据已准备完成"
)) {
    if ($source -notmatch [regex]::Escape($required)) {
        throw "demo.ps1 缺少必要契约：$required"
    }
}
if ($source -match "Write-Host.*(token|Token|令牌|凭据)[:：]") {
    throw "demo.ps1 不得打印令牌或凭据内容。"
}
if ($source -match "Remove-Item.*\`$demoRoot.*-Recurse") {
    throw "demo.ps1 不得递归删除演示根目录。"
}

$readmeFirstLine = ($readme -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
if ($readmeFirstLine -notmatch "AgentGate") { throw "README 首行必须是项目中文标题。" }
foreach ($required in @(
    "项目解决什么问题",
    "一键本地准备",
    "POST /api/v1/actions",
    "不提供 Windows 内核驱动",
    "PowerShell 执行策略",
    "停止项目"
)) {
    if ($readme -notmatch [regex]::Escape($required)) {
        throw "README 缺少必要说明：$required"
    }
}
if ($readme -match "ark-[A-Za-z0-9-]{20,}") {
    throw "README 不得包含真实模型令牌。"
}

Write-Output "demo contract checks passed"
