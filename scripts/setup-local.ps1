$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$webRoot = Join-Path $repoRoot "apps\web"
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm.cmd is required for first-run setup."
}
Push-Location $webRoot
npm.cmd ci
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm.cmd ci failed." }
Pop-Location
& (Join-Path $PSScriptRoot "start-local.ps1") -Provider "mock"
$tokenPath = Join-Path $repoRoot "data\bootstrap-token"
Write-Host "首次运行 bootstrap-token 文件路径：$tokenPath"
Write-Host "请在本机受信任的终端中读取该文件并完成 /api/auth/setup；脚本不会打印 token 内容。"
Start-Process "http://localhost:5173"
