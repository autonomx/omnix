param(
    [string]$Scenario = "",
    [switch]$FastMode
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $branch = (& git branch --show-current 2>$null).Trim()
    $head = (& git rev-parse HEAD 2>$null).Trim()
    if ($LASTEXITCODE -eq 0 -and $head) {
        $branchLabel = $(if ($branch) { $branch } else { "(detached)" })
        Write-Host "Repository head: $branchLabel @ $head"

        if ($branch) {
            $remoteRef = "refs/remotes/origin/$branch"
            $remoteHead = (& git rev-parse --verify $remoteRef 2>$null)
            if ($LASTEXITCODE -eq 0 -and $remoteHead) {
                $remoteHead = $remoteHead.Trim()
                if ($remoteHead -ne $head) {
                    Write-Warning (
                        "Local HEAD differs from origin/$branch ($remoteHead). " +
                        "Live results may not match the current remote branch."
                    )
                }
            }
        }

        $trackedChanges = @(& git status --porcelain --untracked-files=no 2>$null)
        if ($LASTEXITCODE -eq 0 -and $trackedChanges.Count -gt 0) {
            Write-Warning (
                "Tracked working-tree changes are present. " +
                "Live results may not match the printed commit exactly."
            )
        }
    }

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
