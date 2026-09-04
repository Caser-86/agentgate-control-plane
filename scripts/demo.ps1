[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 18230,
    [ValidateRange(1, 65535)]
    [int]$WebPort = 15173,
    [switch]$ResetDemoData,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $repoRoot

function Invoke-LocalApi {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [ValidateSet("GET", "POST", "PATCH", "DELETE")][string]$Method = "GET",
        [hashtable]$Headers = @{},
        [object]$Body,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $request = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        TimeoutSec = 15
    }
    if ($PSBoundParameters.ContainsKey("Body")) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Depth 8 -Compress
    }
    try {
        return Invoke-RestMethod @request
    } catch {
        throw "$FailureMessage。请先确认 API 已启动，并检查本地服务状态。"
    }
}

function Wait-ApiHealth {
    param([Parameter(Mandatory = $true)][string]$Uri)

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri $Uri -TimeoutSec 3
            if ($health.status -eq "ok") { return $health }
        } catch {
            # API 正在启动，继续使用有界轮询。
        }
        Start-Sleep -Seconds 2
    }
    throw "API 在 90 秒内没有就绪。请运行 docker compose ps 查看容器状态。"
}

function Test-ReparsePoint {
    param([Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item)
    return (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Assert-DemoDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolved = [System.IO.Path]::GetFullPath($Path)
    $localAppData = [System.IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd("\")
    $requiredPrefix = "$localAppData\AgentGate\demo-workspace"
    if (-not $resolved.Equals($requiredPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝使用非演示目录：$resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        $item = Get-Item -LiteralPath $resolved -Force
        if (-not (Test-ReparsePoint $item)) { return $resolved }
        throw "演示目录不能是符号链接或其他重解析点：$resolved"
    }
    return $resolved
}

function Ensure-DemoFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (Test-ReparsePoint $item) { throw "拒绝写入重解析文件：$Path" }
        Remove-Item -LiteralPath $Path -Force
    }
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Remove-DemoFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    if (Test-ReparsePoint $item) { throw "拒绝删除重解析文件：$Path" }
    Remove-Item -LiteralPath $Path -Force
}

function Get-AdminHeaders {
    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($env:AGENTGATE_SESSION_COOKIE)) {
        $headers.Cookie = "agentgate_session=$($env:AGENTGATE_SESSION_COOKIE)"
    }
    return $headers
}

$demoRoot = Assert-DemoDirectory (Join-Path $env:LOCALAPPDATA "AgentGate\demo-workspace")
$demoParent = Split-Path -Parent $demoRoot
$workerStateDir = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "AgentGate\worker"))
$workerCredentials = Join-Path $workerStateDir "credentials.bin"
$apiBase = "http://127.0.0.1:$ApiPort"
$webUrl = "http://127.0.0.1:$WebPort/files"
$startLocal = Join-Path $PSScriptRoot "start-local.ps1"
$startWorker = Join-Path $PSScriptRoot "start-worker.ps1"
$workerPython = Join-Path $repoRoot "apps\worker\.venv\Scripts\python.exe"

$oldApiPort = $env:AGENTGATE_API_PORT
$oldWebPort = $env:AGENTGATE_WEB_PORT
$oldAllowedRoot = $env:AGENTGATE_WORKSPACE_ALLOWED_ROOT
$enrollmentId = $null

try {
    # 只在当前 PowerShell 子进程和 Compose 子进程中覆盖配置，不改写 .env。
    $env:AGENTGATE_API_PORT = [string]$ApiPort
    $env:AGENTGATE_WEB_PORT = [string]$WebPort
    $env:AGENTGATE_WORKSPACE_ALLOWED_ROOT = $demoParent
    & $startLocal
    if ($LASTEXITCODE -ne 0) { throw "本地服务启动失败。" }
} finally {
    if ($null -eq $oldApiPort) { Remove-Item Env:AGENTGATE_API_PORT -ErrorAction SilentlyContinue } else { $env:AGENTGATE_API_PORT = $oldApiPort }
    if ($null -eq $oldWebPort) { Remove-Item Env:AGENTGATE_WEB_PORT -ErrorAction SilentlyContinue } else { $env:AGENTGATE_WEB_PORT = $oldWebPort }
    if ($null -eq $oldAllowedRoot) { Remove-Item Env:AGENTGATE_WORKSPACE_ALLOWED_ROOT -ErrorAction SilentlyContinue } else { $env:AGENTGATE_WORKSPACE_ALLOWED_ROOT = $oldAllowedRoot }
}

$health = Wait-ApiHealth "$apiBase/health"
$adminHeaders = Get-AdminHeaders
$auth = Invoke-LocalApi -Uri "$apiBase/api/auth/status" -Headers $adminHeaders -FailureMessage "读取认证状态失败"
if (-not $auth.authenticated) {
    if ([string]::IsNullOrWhiteSpace($env:AGENTGATE_SESSION_COOKIE)) {
        throw "当前启用了管理员认证。请先在浏览器登录，或在本机进程环境中提供 AGENTGATE_SESSION_COOKIE；脚本不会读取或打印密码。"
    }
    throw "管理员会话已失效，请刷新浏览器后重新登录。"
}
if (-not [string]::IsNullOrWhiteSpace($env:AGENTGATE_SESSION_COOKIE)) {
    $csrf = $env:AGENTGATE_CSRF_TOKEN
    if ([string]::IsNullOrWhiteSpace($csrf)) {
        $csrfResponse = Invoke-LocalApi -Uri "$apiBase/api/auth/csrf" -Headers $adminHeaders -FailureMessage "读取 CSRF 校验失败"
        $csrf = [string]$csrfResponse.csrf_token
    }
    if ([string]::IsNullOrWhiteSpace($csrf)) { throw "管理员会话没有可用的 CSRF 校验。" }
    $adminHeaders["X-CSRF-Token"] = $csrf
    $adminHeaders["Origin"] = "http://127.0.0.1:$WebPort"
}

if (-not (Test-Path -LiteralPath $workerPython -PathType Leaf)) {
    throw "找不到 Native Worker 运行环境，请先执行 .\scripts\setup-local.ps1。"
}
$dedicatedWorkerRunning = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -in @("python.exe", "powershell.exe") -and
        $_.CommandLine -like "*agentgate_worker.main*" -and
        $_.CommandLine -like "*$workerStateDir*"
    }
).Count -gt 0
$workerReady = ($health.checks.worker.status -eq "ok") -and
    (Test-Path -LiteralPath $workerCredentials -PathType Leaf) -and
    $dedicatedWorkerRunning
if (-not $workerReady) {
    $enrollment = $null
    if (-not (Test-Path -LiteralPath $workerCredentials -PathType Leaf)) {
        $enrollment = Invoke-LocalApi -Method POST -Uri "$apiBase/api/auth/tokens" -Headers $adminHeaders -Body @{
            name = "本地文件治理 Worker 注册"
            scopes = @("worker:enroll")
            expires_in_seconds = 600
        } -FailureMessage "创建 Worker 注册凭据失败"
        $enrollmentId = [string]$enrollment.id
    }
    $workerLogRoot = Join-Path $env:LOCALAPPDATA "AgentGate"
    New-Item -ItemType Directory -Path $workerLogRoot -Force | Out-Null
    $workerStdout = Join-Path $workerLogRoot "worker-demo.stdout.log"
    $workerStderr = Join-Path $workerLogRoot "worker-demo.stderr.log"
    $workerArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startWorker,
        "-Continuous", "-ApiUrl", $apiBase, "-StateDir", $workerStateDir
    )
    if ($enrollment) { $workerArgs += @("-EnrollmentToken", [string]$enrollment.token) }
    $workerArgumentLine = ($workerArgs | ForEach-Object {
        '"' + ([string]$_).Replace('"', '\"') + '"'
    }) -join " "
    $workerProcess = Start-Process -FilePath "powershell.exe" -ArgumentList $workerArgumentLine `
        -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $workerStdout `
        -RedirectStandardError $workerStderr -PassThru
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $health = Invoke-RestMethod -Uri "$apiBase/api/platform/health" -TimeoutSec 3
            if ($health.checks.worker.status -eq "ok") { $workerReady = $true; break }
        } catch {
            # Worker 注册或首次心跳尚未完成。
        }
        if ($workerProcess.HasExited) { break }
    }
    if (-not $workerReady) {
        throw "Native Worker 在 45 秒内没有上线。请查看 $workerStderr；脚本没有输出任何凭据。"
    }
}

$workspaces = @(Invoke-LocalApi -Uri "$apiBase/api/v1/workspaces" -Headers $adminHeaders -FailureMessage "读取受管工作区失败")
$workspace = $workspaces | Where-Object {
    ([string]$_.root_path).Equals($demoRoot, [StringComparison]::OrdinalIgnoreCase)
} | Select-Object -First 1
if ($null -eq $workspace) {
    $workspace = Invoke-LocalApi -Method POST -Uri "$apiBase/api/v1/workspaces" -Headers $adminHeaders -Body @{
        name = "AgentGate 文件治理工作区"
        root_path = $demoRoot
    } -FailureMessage "登记文件治理工作区失败"
} elseif (-not $workspace.enabled) {
    $workspace = Invoke-LocalApi -Method PATCH -Uri "$apiBase/api/v1/workspaces/$($workspace.id)" -Headers $adminHeaders -Body @{ enabled = $true } -FailureMessage "启用文件治理工作区失败"
}

New-Item -ItemType Directory -Path $demoRoot -Force | Out-Null
if ($ResetDemoData) {
    Remove-DemoFile (Join-Path $demoRoot "demo.txt")
    Remove-DemoFile (Join-Path $demoRoot "demo-secret.txt")
}
Ensure-DemoFile (Join-Path $demoRoot "demo.txt") "AgentGate 文件治理测试文件。内容由脚本生成，不包含真实凭据。"
Ensure-DemoFile (Join-Path $demoRoot "demo-secret.txt") ("演示专用占位内容：" + [Guid]::NewGuid().ToString("N"))

Write-Host "文件治理数据已准备完成。"
Write-Host "API：$apiBase"
Write-Host "Worker：在线"
Write-Host "演示工作区：$demoRoot"
Write-Host "下一步：打开 $webUrl，选择工作区和文件动作。"
if (-not $NoBrowser) { Start-Process $webUrl | Out-Null }
