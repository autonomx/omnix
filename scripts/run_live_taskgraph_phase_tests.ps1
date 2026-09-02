param(
    [string]$Scenario = "",
    [switch]$FastMode
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $env:OMNIX_RUN_LIVE_TASKGRAPH_PHASE_TESTS = "1"
    $env:OMNIX_LIVE_TASKGRAPH_FAST_MODE = $(if ($FastMode) { "1" } else { "0" })

    if ([string]::IsNullOrWhiteSpace($Scenario)) {
        Remove-Item Env:OMNIX_LIVE_TASKGRAPH_SCENARIO -ErrorAction SilentlyContinue
        Write-Host "Running full live TaskGraph Phase 15-19 matrix (GPT-5.6 Luna, high)..."
    }
    else {
        $env:OMNIX_LIVE_TASKGRAPH_SCENARIO = $Scenario
        Write-Host "Running live TaskGraph scenario: $Scenario"
    }

    python -m pytest src/tests/agent_runtime/test_live_taskgraph_phases_15_19.py -q --tb=short

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
