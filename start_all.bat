@echo off
setlocal EnableDelayedExpansion
REM Omnix launcher (Windows). A thin wrapper (WP-11.4): `python -m app.launcher start`
REM checks the interpreters, starts the PostgreSQL container, checks the database,
REM applies migrations, serves the launcher dashboard on http://127.0.0.1:5055 and
REM starts the gateway and web app. This wrapper only finds the app interpreter and
REM loads the protected database credential (Windows DPAPI) before calling it.
REM Interpreters: RPG_FLUX_PYTHON / RPG_TTS_PYTHON / RPG_STT_PYTHON, else
REM resources\config\launcher.toml, else the Conda environments under CONDA_ROOT.
REM
REM   start_all.bat                                   start Omnix
REM   start_all.bat --postgres-only                   only start the PostgreSQL container
REM   start_all.bat --database-credential-injected-check   check without starting services

if not defined CONDA_ROOT set "CONDA_ROOT=%USERPROFILE%\miniconda3"
if not defined RPG_FLUX_PYTHON set "RPG_FLUX_PYTHON=%CONDA_ROOT%\envs\rpg-flux\python.exe"
if not exist "%RPG_FLUX_PYTHON%" (
    echo ERROR: the app runtime is missing: %RPG_FLUX_PYTHON%. Run setup.bat first.
    exit /b 1
)
set "PYTHONPATH=%~dp0src"
if not defined OMNIX_POSTGRES_CONTAINER set "OMNIX_POSTGRES_CONTAINER=omnix-postgres"

set "OMNIX_LAUNCH_MODE="
if /I "%~1"=="--postgres-only" set "OMNIX_LAUNCH_MODE=--postgres-only"
if /I "%~1"=="--database-credential-injected-check" set "OMNIX_LAUNCH_MODE=--check"

if /I not "%~1"=="--postgres-only" if not defined OMNIX_DATABASE_URL (
    if /I "%~1"=="--database-credential-injected" goto :credential_missing
    if /I "%~1"=="--database-credential-injected-check" goto :credential_missing
    echo [POSTGRES] Loading the current-user protected database credential...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage_postgresql_credential.ps1" -Action launch -BatchPath "%~f0"
    set "OMNIX_EXIT_CODE=!ERRORLEVEL!"
    endlocal & exit /b !OMNIX_EXIT_CODE!
)

"%RPG_FLUX_PYTHON%" -m app.launcher start --postgres-container "%OMNIX_POSTGRES_CONTAINER%" %OMNIX_LAUNCH_MODE%
set "OMNIX_EXIT_CODE=%ERRORLEVEL%"
REM Keep a double-clicked window open on failure.
if not "%OMNIX_EXIT_CODE%"=="0" if not defined OMNIX_LAUNCH_MODE pause
endlocal & exit /b %OMNIX_EXIT_CODE%

:credential_missing
echo ERROR: The protected PostgreSQL credential loader did not inject OMNIX_DATABASE_URL.
endlocal & exit /b 1
