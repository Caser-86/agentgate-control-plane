[CmdletBinding()]
param(
    [string]$ApiUrl = "",
    [int]$ApiPort = 0,
    [string]$StateDir = "",
    [ValidateLength(1, 80)]
    [string]$Name = "本机 Worker",
    [ValidateRange(60, 3600)]
    [int]$ExpiresInSeconds = 600,
    [ValidateRange(0.1, 60.0)]
    [double]$PollSeconds = 1.0,
    [ValidateRange(1.0, 60.0)]
    [double]$HeartbeatSeconds = 10.0
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Resolve-ApiUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][int]$Port
    )

    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        return $Value
    }
    if ($Port -eq 0) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "未提供 ApiUrl，且找不到 Docker CLI，无法推导 Compose API 端口。"
        }
        Push-Location $repoRoot
        try {
            $configJson = docker compose config --format json
            if ($LASTEXITCODE -ne 0) { throw "docker compose config 失败。" }
            $config = $configJson | ConvertFrom-Json
            $bindings = @($config.services.api.ports | Where-Object {
                [int]$_.target -eq 8000 -and $_.host_ip -eq "127.0.0.1"
            })
            if ($bindings.Count -ne 1) {
                throw "Compose API 必须只有一个回环端口绑定。"
            }
            $Port = [int]$bindings[0].published
        } finally {
            Pop-Location
        }
    }
    if ($Port -lt 1 -or $Port -gt 65535) {
        throw "ApiPort 必须在 1 到 65535 之间。"
    }
    return "http://127.0.0.1:$Port"
}

function Assert-LoopbackApiUrl {
    param([Parameter(Mandatory = $true)][string]$Value)

    $parsed = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -notin @("http", "https") -or
        [string]::IsNullOrWhiteSpace($parsed.DnsSafeHost) -or
        $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment -or
        $parsed.AbsolutePath -notin @("", "/")) {
        throw "API URL 必须是没有凭据、查询参数和路径的 HTTP(S) 回环地址。"
    }
    $hostName = $parsed.DnsSafeHost.ToLowerInvariant().TrimEnd('.')
    if ($hostName -notin @("localhost", "127.0.0.1", "::1")) {
        throw "只允许连接本机回环 API，不支持远程 Worker 注册。"
    }
    return $parsed
}

function Invoke-LocalApi {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [ValidateSet("GET", "POST")][string]$Method = "GET",
        [hashtable]$Headers = @{},
        [object]$Body
    )

    $request = @{ Method = $Method; Uri = $Uri; Headers = $Headers; TimeoutSec = 15 }
    if ($PSBoundParameters.ContainsKey("Body")) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Depth 8 -Compress
    }
    return Invoke-RestMethod @request
}

$ApiUrl = Resolve-ApiUrl -Value $ApiUrl -Port $ApiPort
$parsedApiUrl = Assert-LoopbackApiUrl $ApiUrl
$statePath = if ([string]::IsNullOrWhiteSpace($StateDir)) {
    Join-Path $env:LOCALAPPDATA "AgentGate\worker"
} else {
    $StateDir
}
$statePath = [System.IO.Path]::GetFullPath($statePath)
$credentialsPath = Join-Path $statePath "credentials.bin"
if (Test-Path -LiteralPath $credentialsPath -PathType Leaf) {
    throw "Worker 状态目录已有凭据，为避免覆盖请指定新的 StateDir：$statePath"
}
if (Test-Path -LiteralPath $statePath) {
    $stateItem = Get-Item -LiteralPath $statePath -Force
    if (($stateItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Worker 状态目录不能是符号链接或其他重解析点：$statePath"
    }
} else {
    New-Item -ItemType Directory -Path $statePath -Force | Out-Null
}

$headers = @{}
if (-not [string]::IsNullOrWhiteSpace($env:AGENTGATE_SESSION_COOKIE)) {
    $headers.Cookie = "agentgate_session=$($env:AGENTGATE_SESSION_COOKIE)"
    $csrf = $env:AGENTGATE_CSRF_TOKEN
    if ([string]::IsNullOrWhiteSpace($csrf)) {
        $csrfResponse = Invoke-LocalApi -Uri "$ApiUrl/api/auth/csrf" -Headers $headers
        $csrf = [string]$csrfResponse.csrf_token
    }
    if ([string]::IsNullOrWhiteSpace($csrf)) {
        throw "管理员会话没有可用的 CSRF 校验，请先在本机登录。"
    }
    $headers["X-CSRF-Token"] = $csrf
    $headers.Origin = "http://127.0.0.1:$($env:AGENTGATE_WEB_PORT ?? 5173)"
}

try {
    $enrollment = Invoke-LocalApi -Method POST -Uri "$ApiUrl/api/auth/tokens" -Headers $headers -Body @{
        name = $Name
        scopes = @("worker:enroll")
        expires_in_seconds = $ExpiresInSeconds
    }
} catch {
    throw "创建 Worker 一次性注册令牌失败。请确认管理员会话有效，或当前处于本机免密模式。"
}
if ([string]::IsNullOrWhiteSpace([string]$enrollment.token)) {
    throw "本机 API 没有返回有效的 Worker 注册令牌。"
}

$logRoot = Join-Path $env:LOCALAPPDATA "AgentGate"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$stdoutPath = Join-Path $logRoot "worker-live.stdout.log"
$stderrPath = Join-Path $logRoot "worker-live.stderr.log"
$registrationStdoutPath = Join-Path $logRoot "worker-registration.stdout.log"
$registrationStderrPath = Join-Path $logRoot "worker-registration.stderr.log"
$startWorker = Join-Path $PSScriptRoot "start-worker.ps1"
$pwsh = (Get-Command pwsh).Source
$registrationArguments = @(
    "-NoProfile", "-File", $startWorker,
    "-ApiUrl", $ApiUrl,
    "-StateDir", $statePath
)
$registrationArgumentLine = ($registrationArguments | ForEach-Object {
    '"' + ([string]$_).Replace('"', '\"') + '"'
}) -join " "
$registrationProcess = Start-Process -FilePath $pwsh -ArgumentList $registrationArgumentLine -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -RedirectStandardOutput $registrationStdoutPath -RedirectStandardError $registrationStderrPath `
    -Environment @{ AGENTGATE_WORKER_ENROLLMENT_TOKEN = [string]$enrollment.token } -Wait -PassThru
$enrollment = $null
if ($registrationProcess.ExitCode -ne 0) {
    throw "Worker 首次注册失败（退出码：$($registrationProcess.ExitCode)）。请查看 $registrationStderrPath。"
}

$workerArguments = @(
    "-NoProfile", "-File", $startWorker,
    "-ApiUrl", $ApiUrl,
    "-StateDir", $statePath,
    "-Continuous",
    "-PollSeconds", $PollSeconds,
    "-HeartbeatSeconds", $HeartbeatSeconds
)
$workerArgumentLine = ($workerArguments | ForEach-Object {
    '"' + ([string]$_).Replace('"', '\"') + '"'
}) -join " "
$workerProcess = Start-Process -FilePath $pwsh -ArgumentList $workerArgumentLine -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru

$deadline = (Get-Date).AddSeconds(45)
$workerStatus = "unknown"
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds ([Math]::Max(1, [int][Math]::Ceiling($PollSeconds)))
    if ($workerProcess.HasExited) { break }
    try {
        $health = Invoke-LocalApi -Uri "$ApiUrl/api/platform/health"
        $workerStatus = [string]$health.checks.worker.status
        if ($workerStatus -eq "ok") { break }
    } catch {
        $workerStatus = "request_failed"
    }
}

if ($workerStatus -ne "ok") {
    if (-not $workerProcess.HasExited) {
        Stop-Process -Id $workerProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw "Worker 未能在 45 秒内上线（状态：$workerStatus）。请查看 $stderrPath；注册令牌不会写入日志。"
}

Write-Host "Native Worker 已注册并上线。"
Write-Host "Worker 进程 PID：$($workerProcess.Id)"
Write-Host "状态目录：$statePath"
Write-Host "日志：$stdoutPath / $stderrPath"
