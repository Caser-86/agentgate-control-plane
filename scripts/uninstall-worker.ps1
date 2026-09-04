[CmdletBinding()]
param(
    [ValidatePattern("^[A-Za-z0-9_. -]{1,128}$")]
    [string]$TaskName = "AgentGateNativeWorker"
)

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Windows 登录自启动任务不存在：$TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "已移除 Windows 登录自启动任务：$TaskName"
