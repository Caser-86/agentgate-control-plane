[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiUrl,
    [string]$StateDir = "",
    [ValidatePattern("^[A-Za-z0-9_. -]{1,128}$")]
    [string]$TaskName = "AgentGateNativeWorker"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$parsedApiUrl = $null
if (-not [Uri]::TryCreate($ApiUrl, [UriKind]::Absolute, [ref]$parsedApiUrl) -or
    $parsedApiUrl.Scheme -notin @("http", "https") -or
    [string]::IsNullOrWhiteSpace($parsedApiUrl.DnsSafeHost) -or
    $parsedApiUrl.UserInfo -or
    $parsedApiUrl.Query -or
    $parsedApiUrl.Fragment -or
    $parsedApiUrl.AbsolutePath -notin @("", "/")) {
    throw "API URL must be a valid loopback HTTP(S) URL."
}
$loopbackHost = $parsedApiUrl.DnsSafeHost.ToLowerInvariant().TrimEnd('.')
if ($loopbackHost -notin @("localhost", "127.0.0.1", "::1")) {
    throw "Remote API targets are not supported; use the local Compose API loopback URL."
}
try { $null = $parsedApiUrl.Port } catch { throw "API URL must specify a valid port." }

if ([string]::IsNullOrWhiteSpace($StateDir)) {
    $resolvedStateDir = Join-Path $repoRoot "apps\worker\.agentgate-worker"
} elseif ([System.IO.Path]::IsPathRooted($StateDir)) {
    $resolvedStateDir = [System.IO.Path]::GetFullPath($StateDir)
} else {
    $resolvedStateDir = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $StateDir))
}
$credentialPath = Join-Path $resolvedStateDir "credentials.bin"
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
    throw "Worker is not enrolled. Run start-worker.ps1 once before installing auto-start."
}

$startScript = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "start-worker.ps1"))
$actionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -Continuous -ApiUrl `"$ApiUrl`" -StateDir `"$resolvedStateDir`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $env:USERNAME -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started Windows logon task: $TaskName"
Write-Host "Worker API: $ApiUrl"
