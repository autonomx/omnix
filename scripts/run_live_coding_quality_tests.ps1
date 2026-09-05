param(
    [string]$Scenario = "",
    [ValidateSet("standard", "strict", "critical")]
    [string]$RolloutPolicy = "strict",
    [string]$Report = "artifacts/coding-quality-report.json",
    [switch]$EnforceRollout
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:OMNIX_TEST_DATABASE_URL) -and [string]::IsNullOrWhiteSpace($env:OMNIX_DATABASE_URL)) {
    throw "Set OMNIX_TEST_DATABASE_URL or OMNIX_DATABASE_URL before running the live coding quality matrix."
}

$env:OMNIX_RUN_LIVE_CODING_QUALITY_TESTS = "1"
$env:OMNIX_LIVE_CODING_QUALITY_ROLLOUT_POLICY = $RolloutPolicy
$env:OMNIX_LIVE_CODING_QUALITY_REPORT = $Report

if ([string]::IsNullOrWhiteSpace($Scenario)) {
    Remove-Item Env:OMNIX_LIVE_CODING_QUALITY_SCENARIO -ErrorAction SilentlyContinue
} else {
    $env:OMNIX_LIVE_CODING_QUALITY_SCENARIO = $Scenario
}

if ($EnforceRollout) {
    $env:OMNIX_ENFORCE_LIVE_CODING_QUALITY_ROLLOUT = "1"
} else {
    Remove-Item Env:OMNIX_ENFORCE_LIVE_CODING_QUALITY_ROLLOUT -ErrorAction SilentlyContinue
}

python -m pytest src/tests/agent_runtime/test_live_coding_quality_matrix.py -q -s --tb=short
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (Test-Path $Report) {
    Write-Host "Coding quality report: $Report"
}
