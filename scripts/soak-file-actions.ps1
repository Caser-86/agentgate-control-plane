[CmdletBinding()]
param(
    [ValidateRange(1, 1440)]
    [int]$DurationMinutes = 60,
    [ValidateRange(1, 3600)]
    [int]$IntervalSeconds = 30,
    [Parameter(Mandatory = $true)]
    [string]$WorkspacePath,
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 18230
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $repoRoot
$apiBase = "http://127.0.0.1:$ApiPort"

function Invoke-SoakApi {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [ValidateSet("GET", "POST", "PATCH", "DELETE")][string]$Method = "GET",
        [hashtable]$Headers = @{},
        [object]$Body,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )
    $request = @{ Method = $Method; Uri = $Uri; Headers = $Headers; TimeoutSec = 15 }
    if ($PSBoundParameters.ContainsKey("Body")) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Depth 8 -Compress
    }
    try {
        return Invoke-RestMethod @request
    } catch {
        throw "$FailureMessage。请检查 API、认证会话和 Worker 状态。"
    }
}

function Get-AdminHeaders {
    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($env:AGENTGATE_SESSION_COOKIE)) {
        $headers.Cookie = "agentgate_session=$($env:AGENTGATE_SESSION_COOKIE)"
    }
    return $headers
}

function New-IdempotencyKey([string]$Name, [int]$Index) {
    return "file-soak-$Name-$Index-$([guid]::NewGuid().ToString('N'))"
}

function Wait-Action {
    param(
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][string]$ActionId,
        [Parameter(Mandatory = $true)][string]$HeadersKey
    )
    $headers = @{ Authorization = "Bearer $Token" }
    $deadline = (Get-Date).AddSeconds(45)
    do {
        $status = Invoke-SoakApi -Uri "$apiBase/api/v1/actions/$ActionId" -Headers $headers -FailureMessage "读取文件动作状态失败"
        if ($status.status -notin @("queued", "approved", "running", "auto_approved")) {
            return $status
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "文件动作 $HeadersKey 在 45 秒内没有进入终态。"
}

function Assert-SafeBaseDirectory([string]$Path) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($resolved)
    if ($resolved.TrimEnd("\").Equals($root.TrimEnd("\"), [StringComparison]::OrdinalIgnoreCase)) {
        throw "稳定性测试拒绝使用磁盘根目录。"
    }
    if (-not (Test-Path -LiteralPath $resolved)) {
        New-Item -ItemType Directory -Path $resolved -Force | Out-Null
    }
    $item = Get-Item -LiteralPath $resolved -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "稳定性测试根目录不能是重解析点。"
    }
    return $resolved.TrimEnd("\")
}

function Assert-GeneratedWorkspace([string]$Path, [string]$BasePath) {
    $resolved = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    $prefix = "$([System.IO.Path]::GetFullPath($BasePath).TrimEnd('\'))\agentgate-soak-"
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝清理未确认的稳定性测试目录。"
    }
    $item = Get-Item -LiteralPath $resolved -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "稳定性测试目录不能是重解析点。"
    }
    return $resolved
}

$basePath = Assert-SafeBaseDirectory $WorkspacePath
$runRoot = Join-Path $basePath ("agentgate-soak-" + [guid]::NewGuid().ToString("N"))
$runRoot = [System.IO.Path]::GetFullPath($runRoot)
$logRoot = Join-Path $repoRoot "data"
$logPath = Join-Path $logRoot ("file-action-soak-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
$adminHeaders = Get-AdminHeaders
$externalToken = $null
$externalTokenId = $null
$workspace = $null
$iterations = 0
$successes = 0
$failures = 0
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

try {
    $health = Invoke-SoakApi -Uri "$apiBase/api/platform/health" -FailureMessage "读取平台健康状态失败"
    if ($health.status -ne "ok" -or $health.checks.worker.status -ne "ok") {
        throw "API 或 Native Worker 未就绪，稳定性测试不会在 Worker 离线时开始。"
    }
    $auth = Invoke-SoakApi -Uri "$apiBase/api/auth/status" -Headers $adminHeaders -FailureMessage "读取认证状态失败"
    if (-not $auth.authenticated) {
        throw "当前启用了管理员认证；请先登录，并通过 AGENTGATE_SESSION_COOKIE 提供本机会话，脚本不会读取密码。"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:AGENTGATE_SESSION_COOKIE)) {
        $csrf = $env:AGENTGATE_CSRF_TOKEN
        if ([string]::IsNullOrWhiteSpace($csrf)) {
            $csrf = [string](Invoke-SoakApi -Uri "$apiBase/api/auth/csrf" -Headers $adminHeaders -FailureMessage "读取 CSRF 校验失败").csrf_token
        }
        if ([string]::IsNullOrWhiteSpace($csrf)) { throw "管理员会话没有可用的 CSRF 校验。" }
        $adminHeaders["X-CSRF-Token"] = $csrf
        $adminHeaders["Origin"] = "http://127.0.0.1:15173"
    }

    $workspace = Invoke-SoakApi -Method POST -Uri "$apiBase/api/v1/workspaces" -Headers $adminHeaders -Body @{
        name = "文件动作稳定性测试-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
        root_path = $runRoot
    } -FailureMessage "登记稳定性测试工作区失败"
    $external = Invoke-SoakApi -Method POST -Uri "$apiBase/api/auth/tokens" -Headers $adminHeaders -Body @{
        name = "文件动作稳定性测试临时令牌"
        scopes = @("propose:actions")
        expires_in_seconds = [Math]::Max(600, $DurationMinutes * 60 + 300)
    } -FailureMessage "创建稳定性测试临时令牌失败"
    $externalToken = [string]$external.token
    $externalTokenId = [string]$external.id

    while ($stopwatch.Elapsed.TotalMinutes -lt $DurationMinutes) {
        $iterations++
        $caseRoot = Join-Path $runRoot ("case-$iterations")
        New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
        $relativePath = "case-$iterations/demo.txt"
        $filePath = Join-Path $caseRoot "demo.txt"
        $content = [System.Text.UTF8Encoding]::new($false).GetBytes("AgentGate soak iteration $iterations")
        [System.IO.File]::WriteAllBytes($filePath, $content)
        $expectedDigest = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $externalHeaders = @{ Authorization = "Bearer $externalToken" }

        try {
            $inspect = Invoke-SoakApi -Method POST -Uri "$apiBase/api/v1/actions" -Headers (@{
                Authorization = "Bearer $externalToken"
                "Idempotency-Key" = New-IdempotencyKey "inspect" $iterations
            }) -Body @{
                action = "file.inspect.v1"
                workspace_id = $workspace.id
                relative_path = $relativePath
            } -FailureMessage "提交文件检查失败"
            $inspectStatus = Wait-Action $externalToken $inspect.id "inspect-$iterations"
            if ($inspectStatus.status -ne "succeeded" -or $inspectStatus.result.content_sha256 -ne $expectedDigest) {
                throw "只读检查结果与磁盘摘要不一致。"
            }

            $quarantineKey = New-IdempotencyKey "quarantine" $iterations
            $quarantine = Invoke-SoakApi -Method POST -Uri "$apiBase/api/v1/actions" -Headers (@{
                Authorization = "Bearer $externalToken"
                "Idempotency-Key" = $quarantineKey
            }) -Body @{
                action = "file.quarantine.v1"
                workspace_id = $workspace.id
                relative_path = $relativePath
                reason = "稳定性测试"
            } -FailureMessage "提交文件隔离失败"
            if ($quarantine.status -ne "pending_approval" -or -not (Test-Path -LiteralPath $filePath)) {
                throw "未审批文件没有保持原磁盘状态。"
            }
            $replay = Invoke-SoakApi -Method POST -Uri "$apiBase/api/v1/actions" -Headers (@{
                Authorization = "Bearer $externalToken"
                "Idempotency-Key" = $quarantineKey
            }) -Body @{
                action = "file.quarantine.v1"
                workspace_id = $workspace.id
                relative_path = $relativePath
                reason = "稳定性测试"
            } -FailureMessage "重放文件隔离失败"
            if ([string]$replay.id -ne [string]$quarantine.id) { throw "重复幂等键创建了第二个文件动作。" }
            Invoke-SoakApi -Method POST -Uri "$apiBase/api/approvals/$($quarantine.id)/approve" -Headers $adminHeaders -Body @{ note = "稳定性测试批准" } -FailureMessage "批准文件隔离失败" | Out-Null
            $quarantined = Wait-Action $externalToken $quarantine.id "quarantine-$iterations"
            if ($quarantined.status -ne "succeeded" -or $quarantined.result.side_effect -ne "quarantined" -or (Test-Path -LiteralPath $filePath)) {
                throw "隔离后的 API 状态与磁盘状态不一致。"
            }

            $restoreKey = New-IdempotencyKey "restore" $iterations
            $restore = Invoke-SoakApi -Method POST -Uri "$apiBase/api/v1/actions" -Headers (@{
                Authorization = "Bearer $externalToken"
                "Idempotency-Key" = $restoreKey
            }) -Body @{
                action = "file.restore.v1"
                workspace_id = $workspace.id
                quarantine_entry_id = $quarantined.result.quarantine_entry_id
            } -FailureMessage "提交文件恢复失败"
            if ($restore.status -ne "pending_approval") { throw "恢复动作没有进入审批状态。" }
            Invoke-SoakApi -Method POST -Uri "$apiBase/api/approvals/$($restore.id)/approve" -Headers $adminHeaders -Body @{ note = "稳定性测试恢复" } -FailureMessage "批准文件恢复失败" | Out-Null
            $restored = Wait-Action $externalToken $restore.id "restore-$iterations"
            $actualDigest = if (Test-Path -LiteralPath $filePath) { (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }
            if ($restored.status -ne "succeeded" -or $restored.result.side_effect -ne "restored" -or $actualDigest -ne $expectedDigest) {
                throw "恢复后的 API 状态与磁盘摘要不一致。"
            }
            $successes++
            @{ iteration = $iterations; status = "pass"; latency_ms = [int]$stopwatch.ElapsedMilliseconds; side_effects = @("quarantined", "restored") } | ConvertTo-Json -Compress | Add-Content -LiteralPath $logPath -Encoding UTF8
        } catch {
            $failures++
            @{ iteration = $iterations; status = "fail"; error = "file_action_assertion_failed" } | ConvertTo-Json -Compress | Add-Content -LiteralPath $logPath -Encoding UTF8
            throw "文件动作稳定性测试第 $iterations 次失败；已写入脱敏日志 $logPath。"
        }
        if ($stopwatch.Elapsed.TotalMinutes -lt $DurationMinutes) { Start-Sleep -Seconds $IntervalSeconds }
    }
    if ($iterations -lt 1) { throw "稳定性测试没有产生有效样本。" }
} finally {
    if ($externalTokenId) {
        Invoke-SoakApi -Method DELETE -Uri "$apiBase/api/auth/tokens/$externalTokenId" -Headers $adminHeaders -FailureMessage "清理稳定性测试令牌失败" 2>$null | Out-Null
    }
    if ($workspace -and $adminHeaders) {
        Invoke-SoakApi -Method PATCH -Uri "$apiBase/api/v1/workspaces/$($workspace.id)" -Headers $adminHeaders -Body @{ enabled = $false } -FailureMessage "停用稳定性测试工作区失败" 2>$null | Out-Null
    }
    if (Test-Path -LiteralPath $runRoot) {
        $safeRunRoot = Assert-GeneratedWorkspace $runRoot $basePath
        Remove-Item -LiteralPath $safeRunRoot -Recurse -Force
    }
}

Write-Host "文件动作稳定性测试完成：样本 $iterations，成功 $successes，失败 $failures。"
Write-Host "脱敏 JSONL 日志：$logPath"
