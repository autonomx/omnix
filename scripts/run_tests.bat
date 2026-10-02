@echo off
setlocal
set "OMNIX_REPO_ROOT=%~dp0.."
for %%I in ("%OMNIX_REPO_ROOT%") do set "OMNIX_REPO_ROOT=%%~fI"
cd /d "%OMNIX_REPO_ROOT%"
if errorlevel 1 exit /b 1

REM Dependencies are installed by the repository setup, not by this runner.
REM PostgreSQL tests require an explicit disposable OMNIX_TEST_DATABASE_URL.
set "TEST_TYPE=%~1"
if "%TEST_TYPE%"=="" set "TEST_TYPE=all"

if "%TEST_TYPE%"=="unit" (
    python -m pytest src/tests/unit/ -v --tb=short
) else if "%TEST_TYPE%"=="api" (
    python -m pytest src/tests/api/ -v --tb=short
) else if "%TEST_TYPE%"=="integration" (
    python -m pytest src/tests/integration/ -v --tb=short
) else if "%TEST_TYPE%"=="all" (
    python -m pytest src/tests/ -v --tb=short
) else if "%TEST_TYPE%"=="coverage" (
    python -m pytest src/tests/ -v --tb=short --cov=src --cov-report=html --cov-report=term
) else (
    echo Usage: scripts\run_tests.bat [unit^|api^|integration^|all^|coverage]
    exit /b 2
)
exit /b %errorlevel%
