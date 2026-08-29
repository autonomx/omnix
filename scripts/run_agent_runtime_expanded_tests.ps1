param(
    [int]$PostgresPort = 55432,
    [switch]$KeepDatabase
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "docker-compose.agent-tests.yml"
$databaseUrl = "postgresql://omnix_test:omnix_test@127.0.0.1:$PostgresPort/omnix_test"

Push-Location $repoRoot
try {
    Write-Host "Checking PostgreSQL Python dependencies..."
    python -c "import psycopg; import psycopg_pool" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing PostgreSQL Python test dependencies..."
        python -m pip install "psycopg[binary]>=3.2.1,<4" "psycopg-pool>=3.2.1,<4"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install PostgreSQL Python test dependencies."
        }
    }

    $env:OMNIX_AGENT_TEST_POSTGRES_PORT = "$PostgresPort"

    Write-Host "Starting isolated Agent Runtime PostgreSQL on port $PostgresPort..."
    docker compose -f $composeFile down --remove-orphans 2>$null
    docker compose -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start isolated Agent Runtime PostgreSQL."
    }

    Write-Host "Waiting for PostgreSQL health..."
    $healthy = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        docker compose -f $composeFile exec -T postgres-agent-tests pg_isready -U omnix_test -d omnix_test *> $null
        if ($LASTEXITCODE -eq 0) {
            $healthy = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) {
        docker compose -f $composeFile logs postgres-agent-tests
        throw "Agent Runtime PostgreSQL did not become healthy."
    }

    $env:OMNIX_TEST_DATABASE_URL = $databaseUrl
    $env:OMNIX_DATABASE_URL = $databaseUrl

    Write-Host "Running expanded Agent Runtime tests against $databaseUrl"
    python -m pytest `
        src/tests/agent_runtime/test_runtime_e2e_matrix.py `
        src/tests/agent_runtime/test_runtime_concurrency.py `
        src/tests/agent_runtime/test_runtime_fault_injection.py `
        src/tests/agent_runtime/test_runtime_security_e2e.py `
        src/tests/agent_runtime/test_runtime_invariants.py `
        src/tests/agent_runtime/test_runtime_performance.py `
        -q --tb=short

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    if (-not $KeepDatabase) {
        Write-Host "Stopping isolated Agent Runtime PostgreSQL..."
        docker compose -f $composeFile down --remove-orphans 2>$null
    }
    Pop-Location
}
