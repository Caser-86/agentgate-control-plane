$ErrorActionPreference = "Stop"
$backupPath = Join-Path $PSScriptRoot "backup-local.ps1"
$restorePath = Join-Path $PSScriptRoot "restore-local.ps1"
$backup = Get-Content -Raw -LiteralPath $backupPath
$restore = Get-Content -Raw -LiteralPath $restorePath

if ($backup -notmatch '\[Parameter\(Mandatory') { throw "备份必须要求明确目标目录。" }
if ($backup -notmatch 'manifest\.json') { throw "备份必须生成 manifest.json。" }
if ($backup -notmatch 'bootstrap-token') { throw "备份必须明确排除 bootstrap-token。" }
if ($backup -notmatch 'Get-FileHash') { throw "备份必须记录文件摘要。" }
if ($backup -notmatch 'agentgate\.db|pg_dump') { throw "备份必须覆盖 SQLite 或 PostgreSQL。" }
if ($restore -notmatch 'ValidateOnly' -or $restore -notmatch 'Apply') { throw "恢复必须区分预检和应用。" }
if ($restore -notmatch 'Offline' -or $restore -notmatch 'CurrentStateBackupDestination') {
    throw "应用恢复必须要求停机确认和当前状态备份。"
}
if ($restore -notmatch 'System\.IO\.File\]::Exists') { throw "恢复必须拒绝覆盖已有文件。" }

Write-Output "backup-restore contract checks passed"
