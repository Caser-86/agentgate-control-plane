[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [switch]$ValidateOnly,
    [switch]$Apply,
    [switch]$Offline,
    [string]$CurrentStateBackupDestination = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Resolve-InputPath([string]$Value) {
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Value))
}

function Test-SameOrChild([string]$Path, [string]$Root) {
    $normalizedPath = $Path.TrimEnd("\")
    $normalizedRoot = $Root.TrimEnd("\")
    return $normalizedPath.Equals($normalizedRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $normalizedPath.StartsWith("$normalizedRoot\", [StringComparison]::OrdinalIgnoreCase)
}

if ($ValidateOnly -and $Apply) {
    throw "-ValidateOnly 和 -Apply 不能同时使用。"
}
if (-not $ValidateOnly -and -not $Apply) {
    $ValidateOnly = $true
}
$sourcePath = Resolve-InputPath $Source
$manifestPath = Join-Path $sourcePath "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "备份缺少 manifest.json：$sourcePath"
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.format_version -ne 1) {
    throw "不支持的备份格式版本：$($manifest.format_version)"
}

foreach ($file in @($manifest.files)) {
    $relative = ([string]$file.path).Replace("/", "\")
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $sourcePath $relative))
    if (-not (Test-SameOrChild $candidate $sourcePath) -or -not [System.IO.File]::Exists($candidate)) {
        throw "备份文件缺失或越界：$relative"
    }
    $actual = Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    if ($actual.Hash -ine [string]$file.sha256) {
        throw "备份摘要不匹配：$relative"
    }
    if ((Get-Item -LiteralPath $candidate).Length -ne [int64]$file.bytes) {
        throw "备份大小不匹配：$relative"
    }
}

if ($ValidateOnly) {
    Write-Output ("备份预检通过：{0}；文件数={1}；数据库类型={2}" -f $sourcePath, @($manifest.files).Count, $manifest.database.type)
    exit 0
}
if (-not $Offline) {
    throw "应用恢复前必须显式指定 -Offline，并先停止 API、scheduler、control-worker、Web 和 Worker。"
}
if ([string]::IsNullOrWhiteSpace($CurrentStateBackupDestination)) {
    throw "应用恢复前必须提供 -CurrentStateBackupDestination 保存当前状态。"
}
if ($manifest.database.type -ne "sqlite") {
    throw "PostgreSQL 备份已完成摘要预检；本脚本暂不自动应用 PostgreSQL 恢复，请在停机窗口使用受审计的 psql 流程。"
}

$currentBackup = Resolve-InputPath $CurrentStateBackupDestination
if (Test-SameOrChild $currentBackup $sourcePath) {
    throw "当前状态备份不能位于待恢复备份目录内。"
}
$backupScript = Join-Path $PSScriptRoot "backup-local.ps1"
& $backupScript -Destination $currentBackup
if ($LASTEXITCODE -ne 0) {
    throw "恢复前的当前状态备份失败，已停止恢复。"
}

$databaseSource = Join-Path $sourcePath ([string]$manifest.database.path).Replace("/", "\")
$databaseTarget = Join-Path $repoRoot "data\agentgate.db"
$stagingTarget = "$databaseTarget.restore-$([guid]::NewGuid().ToString('N'))"
$quarantinePlans = [System.Collections.Generic.List[object]]::new()
$journalPlan = $null
if ($manifest.worker_journal.included -eq $true) {
    $journalSource = Join-Path $sourcePath ([string]$manifest.worker_journal.path).Replace("/", "\")
    $journalTarget = Join-Path ([string]$manifest.worker_journal.source_root) "journal.db"
    if (-not [System.IO.File]::Exists($journalSource)) {
        throw "Worker journal 备份文件缺失。"
    }
    if (Test-SameOrChild ([System.IO.Path]::GetFullPath($journalTarget)) $sourcePath) {
        throw "Worker journal 恢复目标不能位于备份目录内。"
    }
    $journalPlan = [ordered]@{ source = $journalSource; destination = $journalTarget }
}
foreach ($root in @($manifest.quarantine_roots)) {
    $rootSource = Join-Path $sourcePath ([string]$root.backup_path).Replace("/", "\")
    $destinationRoot = [System.IO.Path]::GetFullPath([string]$root.source_root)
    if (Test-SameOrChild $destinationRoot $sourcePath) {
        throw "隔离目录恢复目标不能位于备份目录内。"
    }
    foreach ($file in Get-ChildItem -LiteralPath $rootSource -File -Recurse) {
        $relative = [System.IO.Path]::GetRelativePath($rootSource, $file.FullName)
        $destination = [System.IO.Path]::GetFullPath((Join-Path $destinationRoot $relative))
        if (-not (Test-SameOrChild $destination $destinationRoot)) {
            throw "隔离文件恢复目标越界：$relative"
        }
        if ([System.IO.File]::Exists($destination)) {
            throw "恢复会覆盖已有文件，已停止：$destination"
        }
        $quarantinePlans.Add([ordered]@{ source = $file.FullName; destination = $destination })
    }
}

$createdDirectories = [System.Collections.Generic.List[string]]::new()
$stagingJournal = $null
try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $databaseTarget) -Force | Out-Null
    Copy-Item -LiteralPath $databaseSource -Destination $stagingTarget
    Move-Item -LiteralPath $stagingTarget -Destination $databaseTarget -Force
    if ($null -ne $journalPlan) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $journalPlan.destination) -Force | Out-Null
        $stagingJournal = "$($journalPlan.destination).restore-$([guid]::NewGuid().ToString('N'))"
        Copy-Item -LiteralPath $journalPlan.source -Destination $stagingJournal
        Move-Item -LiteralPath $stagingJournal -Destination $journalPlan.destination -Force
    }
    foreach ($plan in $quarantinePlans) {
        $parent = Split-Path -Parent $plan.destination
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            $createdDirectories.Add($parent)
        }
        Copy-Item -LiteralPath $plan.source -Destination $plan.destination
    }
} finally {
    if (Test-Path -LiteralPath $stagingTarget) {
        Remove-Item -LiteralPath $stagingTarget -Force
    }
    if ($null -ne $stagingJournal -and (Test-Path -LiteralPath $stagingJournal)) {
        Remove-Item -LiteralPath $stagingJournal -Force
    }
}
Write-Output ("恢复已应用：数据库和 {0} 个隔离文件；当前状态备份：{1}" -f $quarantinePlans.Count, $currentBackup)
