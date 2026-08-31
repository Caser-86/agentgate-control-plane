[CmdletBinding()]
param(
    [string]$ApiUrl = "http://127.0.0.1:8000",
    [string]$StateDir = ".agentgate-worker",
    [string]$EnrollmentToken = $env:AGENTGATE_WORKER_ENROLLMENT_TOKEN
)

$workerRoot = Join-Path $PSScriptRoot "..\apps\worker"
$python = Join-Path $PSScriptRoot "..\apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Create the API virtual environment first: apps/api/.venv/Scripts/python.exe was not found."
}
Push-Location $workerRoot
try {
    & $python -m agentgate_worker.main --api-url $ApiUrl --state-dir $StateDir --enrollment-token $EnrollmentToken
} finally {
    Pop-Location
}
