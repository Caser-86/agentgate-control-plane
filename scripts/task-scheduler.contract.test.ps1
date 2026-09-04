$ErrorActionPreference = "Stop"
$install = Join-Path $PSScriptRoot "install-worker.ps1"
$uninstall = Join-Path $PSScriptRoot "uninstall-worker.ps1"
if (-not (Test-Path -LiteralPath $install) -or -not (Test-Path -LiteralPath $uninstall)) {
    throw "Worker Task Scheduler install/uninstall scripts are required."
}

$installSource = Get-Content -Raw -LiteralPath $install
$uninstallSource = Get-Content -Raw -LiteralPath $uninstall
if ($installSource -match "EnrollmentToken|enrollment-token") {
    throw "Task Scheduler arguments must not contain enrollment secrets."
}
if ($installSource -notmatch "Test-Path" -or $installSource -notmatch "credentials\.bin") {
    throw "Task Scheduler installation must require existing DPAPI credentials."
}
if ($installSource -notmatch "New-ScheduledTaskAction") {
    throw "Task Scheduler installation must create a scheduled action."
}
if ($installSource -notmatch "New-ScheduledTaskTrigger.*AtLogOn") {
    throw "Task Scheduler installation must trigger at the current user's logon."
}
if ($installSource -notmatch "MultipleInstances.*IgnoreNew") {
    throw "Task Scheduler installation must avoid duplicate Worker instances."
}
if ($installSource -notmatch "Register-ScheduledTask") {
    throw "Task Scheduler installation must register the task."
}
if ($uninstallSource -notmatch "Get-ScheduledTask" -or $uninstallSource -notmatch "Unregister-ScheduledTask") {
    throw "Task Scheduler uninstall must remove only the registered task."
}
if ($uninstallSource -match "Remove-Item|credentials|journal|StateDir") {
    throw "Task Scheduler uninstall must preserve Worker state."
}

Write-Output "Task Scheduler contract checks passed"
