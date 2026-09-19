$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "start-local.ps1"
$source = Get-Content -Raw -LiteralPath $scriptPath

if ($source -notmatch 'docker compose config --format json') {
    throw "启动脚本必须先解析最终 Compose 配置。"
}
if ($source -notmatch '(?s)docker compose config --format json.*?\$LASTEXITCODE -ne 0') {
    throw "Compose 配置解析失败时必须立即退出。"
}
if ($source -notmatch '(?s)docker compose up -d --build api scheduler control-worker web.*?\$LASTEXITCODE -ne 0') {
    throw "Compose 启动失败时必须返回非零结果。"
}
if ($source -notmatch 'docker compose ps --services --status running') {
    throw "启动脚本必须核对服务是否实际运行。"
}
if ($source -notmatch '(?s)\$requiredService.*?api.*?scheduler.*?control-worker.*?web') {
    throw "启动脚本必须逐项核对 API、scheduler、control-worker 和 Web。"
}
if ($source -notmatch '(?s)Invoke-RestMethod.*?/health.*?\$response\.status -eq "ok"') {
    throw "启动脚本必须等待 API 健康检查，而不是只等待容器启动。"
}

Write-Output "start-local contract checks passed"
