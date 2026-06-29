param(
  [switch]$SkipInstall,
  [string]$EnvFile = ".env.local",
  [string]$BaseUrl = "http://127.0.0.1:8642",
  [string]$TimeoutSeconds = "45"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $RepoRoot $EnvFile }

function Add-EnvIfMissing {
  param([string]$Key, [string]$Value)
  if (-not (Test-Path $EnvPath)) {
    New-Item -ItemType File -Path $EnvPath -Force | Out-Null
  }
  $existing = Get-Content $EnvPath -ErrorAction SilentlyContinue
  if (-not ($existing | Where-Object { $_ -like "$Key=*" })) {
    Add-Content -Path $EnvPath -Value "$Key=$Value"
  }
}

Write-Host "Preparing optional Hermes Agent sidecar setup."
Write-Host "Env file: $EnvPath"

if (-not $SkipInstall) {
  Write-Host "Running the official Hermes Agent installer."
  $installer = Invoke-RestMethod "https://hermes-agent.nousresearch.com/install.ps1"
  Invoke-Expression "& { $installer } -SkipSetup"
} else {
  Write-Host "Skipping Hermes install because -SkipInstall was passed."
}

Add-EnvIfMissing "HERMES_ENABLED" "false"
Add-EnvIfMissing "HERMES_BASE_URL" $BaseUrl
Add-EnvIfMissing "HERMES_TIMEOUT_SECONDS" $TimeoutSeconds

Write-Host "Hermes sidecar env defaults written. Set HERMES_ENABLED=true after starting Hermes."
