[CmdletBinding()]
param(
    [string]$ApiUrl = "",
    [int]$ApiPort = 0,
    [string]$StateDir = ".agentgate-worker",
    [string]$EnrollmentToken = $env:AGENTGATE_WORKER_ENROLLMENT_TOKEN
)

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$apiUrlSupplied = -not [string]::IsNullOrWhiteSpace($ApiUrl)
$parsedApiUrl = $null
if ($apiUrlSupplied) {
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
    try { $urlPort = $parsedApiUrl.Port } catch { throw "API URL must specify a valid port." }
    if ($urlPort -eq -1) {
        $urlPort = if ($parsedApiUrl.Scheme -eq "https") { 443 } else { 80 }
    }
    $ApiPort = [int]$urlPort
}
elseif ($ApiPort -eq 0) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker Desktop is required to derive the Compose API loopback port."
    }
    Push-Location $repoRoot
    try {
        $configJson = docker compose config --format json
        if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }
        $config = $configJson | ConvertFrom-Json
        $apiBindings = @($config.services.api.ports | Where-Object {
            [int]$_.target -eq 8000 -and $_.host_ip -eq "127.0.0.1"
        })
        if ($apiBindings.Count -ne 1) {
            throw "Compose API must have exactly one loopback port binding."
        }
        $ApiPort = [int]$apiBindings[0].published
    } finally {
        Pop-Location
    }
}
if ($ApiPort -eq 0 -and $env:AGENTGATE_API_PORT) { $ApiPort = [int]$env:AGENTGATE_API_PORT }
if ($ApiPort -lt 1 -or $ApiPort -gt 65535) { throw "ApiPort must be between 1 and 65535." }
$workerRoot = Join-Path $PSScriptRoot "..\apps\worker"
$workerRoot = [System.IO.Path]::GetFullPath($workerRoot)
$python = Join-Path $workerRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Create the Worker virtual environment first: apps/worker/.venv/Scripts/python.exe was not found. Run .\scripts\setup-local.ps1."
}
& $python -c "import win32crypt; import agentgate_worker"
if ($LASTEXITCODE -ne 0) {
    throw "Native Worker dependencies are not installed in apps/worker/.venv; run .\scripts\setup-local.ps1."
}
if (-not $apiUrlSupplied) { $ApiUrl = "http://127.0.0.1:$ApiPort" }
Push-Location $workerRoot
try {
    & $python -m agentgate_worker.main --api-url $ApiUrl --state-dir $StateDir --enrollment-token $EnrollmentToken
} finally {
    Pop-Location
}
