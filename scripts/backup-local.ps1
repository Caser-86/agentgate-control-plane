[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [string[]]$QuarantineRoot = @(),
    [string]$WorkerStateDir = "apps\worker\.agentgate-worker"
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

function Assert-DestinationOutside([string]$Source, [string]$BackupPath) {
    if (Test-SameOrChild $BackupPath $Source) {
        throw "备份目录不能位于被备份目录内：$BackupPath"
    }
}

function Add-FileRecord([System.Collections.Generic.List[object]]$Records, [string]$Root, [string]$Path, [string]$Kind) {
    $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
    $relative = [System.IO.Path]::GetRelativePath($Root, $Path).Replace("\", "/")
    $Records.Add([ordered]@{
        kind = $Kind
        path = $relative
        bytes = (Get-Item -LiteralPath $Path).Length
        sha256 = $hash.Hash.ToLowerInvariant()
    })
}

$backupPath = Resolve-InputPath $Destination
if (Test-Path -LiteralPath $backupPath) {
    throw "备份目标已存在，为避免覆盖请使用新的目录：$backupPath"
}
$backupParent = Split-Path -Parent $backupPath
New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
New-Item -ItemType Directory -Path $backupPath | Out-Null

$files = [System.Collections.Generic.List[object]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()
$databaseDir = Join-Path $backupPath "database"
New-Item -ItemType Directory -Path $databaseDir | Out-Null

$sqlitePath = Join-Path $repoRoot "data\agentgate.db"
$database = [ordered]@{}
if (Test-Path -LiteralPath $sqlitePath -PathType Leaf) {
    $apiPython = Join-Path $repoRoot "apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $apiPython -PathType Leaf)) {
        throw "SQLite 一致性备份需要 apps/api/.venv/Scripts/python.exe"
    }
    $databasePath = Join-Path $databaseDir "agentgate.db"
    $sqliteBackupCode = "import sqlite3,sys; source,target=sys.argv[1:]; src=sqlite3.connect(source); dst=sqlite3.connect(target); src.backup(dst); dst.close(); src.close()"
    & $apiPython -c $sqliteBackupCode $sqlitePath $databasePath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
        throw "SQLite 一致性备份失败。"
    }
    $database = [ordered]@{ type = "sqlite"; path = "database/agentgate.db" }
    Add-FileRecord $files $backupPath $databasePath "database"
} else {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "找不到 SQLite 数据库，也找不到 Docker，无法生成数据库备份。"
    }
    $databasePath = Join-Path $databaseDir "agentgate.sql"
    & docker compose exec -T postgres pg_dump -U agentgate -d agentgate --no-owner --no-privileges > $databasePath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
        throw "PostgreSQL 一致性备份失败；请确认 Docker Server、PostgreSQL 和迁移状态。"
    }
    $database = [ordered]@{ type = "postgresql_plain_sql"; path = "database/agentgate.sql" }
    Add-FileRecord $files $backupPath $databasePath "database"
}

$workerStatePath = Resolve-InputPath $WorkerStateDir
$journalPath = Join-Path $workerStatePath "journal.db"
$workerInfo = [ordered]@{ included = $false; path = $null; source_root = $workerStatePath }
if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
    Assert-DestinationOutside $workerStatePath $backupPath
    $workerBackupDir = Join-Path $backupPath "worker"
    New-Item -ItemType Directory -Path $workerBackupDir | Out-Null
    $workerBackupPath = Join-Path $workerBackupDir "journal.db"
    Copy-Item -LiteralPath $journalPath -Destination $workerBackupPath
    $workerInfo = [ordered]@{
        included = $true
        path = "worker/journal.db"
        source_root = $workerStatePath
    }
    Add-FileRecord $files $backupPath $workerBackupPath "worker_journal"
} else {
    $warnings.Add("未找到 Worker journal，备份不包含待对账状态。")
}

$quarantineInfos = [System.Collections.Generic.List[object]]::new()
$rootIndex = 0
foreach ($rootValue in $QuarantineRoot) {
    $sourceRoot = Resolve-InputPath $rootValue
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        throw "隔离目录不存在：$sourceRoot"
    }
    Assert-DestinationOutside $sourceRoot $backupPath
    $backupRelative = "quarantine/root-$rootIndex"
    $quarantinePath = Join-Path $backupPath ("quarantine\root-{0}" -f $rootIndex)
    New-Item -ItemType Directory -Path (Split-Path -Parent $quarantinePath) -Force | Out-Null
    Copy-Item -LiteralPath $sourceRoot -Destination $quarantinePath -Recurse
    $quarantineInfos.Add([ordered]@{
        source_root = $sourceRoot
        backup_path = $backupRelative
    })
    Get-ChildItem -LiteralPath $quarantinePath -File -Recurse | ForEach-Object {
        Add-FileRecord $files $backupPath $_.FullName "quarantine"
    }
    $rootIndex++
}
if ($QuarantineRoot.Count -eq 0) {
    $warnings.Add("未提供隔离目录；备份不包含普通工作区文件或隔离文件。")
}

$manifest = [ordered]@{
    format_version = 1
    created_at = [DateTimeOffset]::Now.ToUniversalTime().ToString("o")
    database = $database
    worker_journal = $workerInfo
    quarantine_roots = @($quarantineInfos)
    files = @($files)
    warnings = @($warnings)
    complete = $warnings.Count -eq 0
    excluded = @("data/bootstrap-token", "Worker credentials.bin", "普通工作区文件")
}
$manifestJson = $manifest | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText((Join-Path $backupPath "manifest.json"), $manifestJson, [Text.UTF8Encoding]::new($false))
Write-Output ("备份已生成：{0}；完整性={1}；文件数={2}" -f $backupPath, $manifest.complete, $files.Count)
