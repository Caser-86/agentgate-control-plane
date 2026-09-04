param(
    [ValidateSet("mock", "openai_compatible")]
    [string]$Provider
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$webRoot = Join-Path $repoRoot "apps\web"
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm.cmd is required for first-run setup."
}
$workerRoot = Join-Path $repoRoot "apps\worker"
$workerVenv = Join-Path $workerRoot ".venv"
$workerPython = Join-Path $workerVenv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $workerPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.11 -m venv $workerVenv
    } else {
        python -m venv $workerVenv
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the local Worker virtual environment at apps/worker/.venv." }
}
& $workerPython -m pip install -e $workerRoot
if ($LASTEXITCODE -ne 0) { throw "Could not install apps/worker dependencies into apps/worker/.venv." }
& $workerPython -c "import win32crypt; import agentgate_worker"
if ($LASTEXITCODE -ne 0) { throw "apps/worker/.venv is missing win32crypt/pywin32; rerun .\scripts\setup-local.ps1." }
Push-Location $webRoot
npm.cmd ci
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm.cmd ci failed." }
Pop-Location
if ($PSBoundParameters.ContainsKey("Provider")) {
    & (Join-Path $PSScriptRoot "start-local.ps1") -Provider $Provider
} else {
    & (Join-Path $PSScriptRoot "start-local.ps1")
}
$tokenPath = Join-Path $repoRoot "data\bootstrap-token"
$configJson = docker compose config --format json
# Compose resolves AGENTGATE_API_PORT and AGENTGATE_WEB_PORT from the environment.
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }
$config = $configJson | ConvertFrom-Json
$webMatches = @($config.services.web.ports | Where-Object { [int]$_.target -eq 80 -and $_.host_ip -eq "127.0.0.1" })
if ($webMatches.Count -ne 1) { throw "Web service must have exactly one loopback port binding." }
$webPort = [int]$webMatches[0].published
$authEnabled = [string]$config.services.api.environment.AGENTGATE_AUTH_ENABLED
if ($authEnabled -eq "true") {
    Write-Host "首次运行 bootstrap-token 文件路径：$tokenPath"
    Write-Host "请在本机受信任的终端中读取该文件并完成 /api/auth/setup；脚本不会打印 token 内容。"
} else {
    Write-Host "当前为本机免密模式，无需 bootstrap-token。"
}
Start-Process "http://127.0.0.1:$webPort"
