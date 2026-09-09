[CmdletBinding()]
param(
  [string]$NodeVersion = "24.20.0",
  [string]$AgentBrowserVersion = "0.36.0",
  # Keep this below the worker npm registry's three-day release-age window.
  [string]$McporterVersion = "0.13.8"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsRoot = Join-Path $RepoRoot ".tools"
$NodeRoot = Join-Path $ToolsRoot "node-v$NodeVersion-win-x64"
$NodeExe = Join-Path $NodeRoot "node.exe"
$NpmCmd = Join-Path $NodeRoot "npm.cmd"
$NpmPrefix = Join-Path $ToolsRoot "npm-global"
$AgentBrowserCmd = Join-Path $NpmPrefix "agent-browser.cmd"
$McporterCmd = Join-Path $NpmPrefix "mcporter.cmd"

New-Item -ItemType Directory -Path $ToolsRoot -Force | Out-Null

function Get-NodeMajor {
  param([string]$Executable)
  try {
    $version = (& $Executable --version 2>$null).Trim()
    if ($version -match '^v?(\d+)') { return [int]$Matches[1] }
  } catch {
  }
  return 0
}

$systemNode = Get-Command node.exe -ErrorAction SilentlyContinue
if ($systemNode -and (Get-NodeMajor $systemNode.Source) -ge 24) {
  $NodeExe = $systemNode.Source
  $NpmCmd = Join-Path (Split-Path -Parent $NodeExe) "npm.cmd"
  Write-Host "Using system Node.js: $(& $NodeExe --version)"
} elseif (-not (Test-Path $NodeExe)) {
  $archive = Join-Path $ToolsRoot "node-v$NodeVersion-win-x64.zip"
  $url = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
  Write-Host "Downloading Node.js $NodeVersion to the repository tool cache."
  Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
  Expand-Archive -LiteralPath $archive -DestinationPath $ToolsRoot -Force
}

if (-not (Test-Path $NodeExe) -or -not (Test-Path $NpmCmd)) {
  throw "Node.js $NodeVersion runtime was not installed correctly."
}

$env:Path = "$(Split-Path -Parent $NodeExe);$NpmPrefix;$env:Path"
Write-Host "Installing agent-browser@$AgentBrowserVersion and mcporter@$McporterVersion."
& $NpmCmd install --global --prefix $NpmPrefix --no-fund --no-audit "agent-browser@$AgentBrowserVersion" "mcporter@$McporterVersion"
if ($LASTEXITCODE -ne 0) { throw "npm failed to install the Omnix agent tools." }

if (-not (Test-Path $AgentBrowserCmd) -or -not (Test-Path $McporterCmd)) {
  throw "The Omnix agent tool command shims were not created under $NpmPrefix."
}

Write-Host "Installing the agent-browser browser payload."
& $AgentBrowserCmd install
if ($LASTEXITCODE -ne 0) { throw "agent-browser browser installation failed." }

[Environment]::SetEnvironmentVariable("OMNIX_AGENT_BROWSER_COMMAND", $AgentBrowserCmd, "User")
[Environment]::SetEnvironmentVariable("OMNIX_AGENT_MCPORTER_COMMAND", $McporterCmd, "User")

Write-Host "Installed agent-browser: $AgentBrowserCmd"
Write-Host "Installed MCPorter: $McporterCmd"
Write-Host "Node runtime: $(& $NodeExe --version)"
