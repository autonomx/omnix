@echo off
setlocal EnableDelayedExpansion

set "RPG_FLUX_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-flux\python.exe"
set "RPG_TTS_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-tts\python.exe"
set "RPG_STT_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-stt\python.exe"

set "OMNIX_TTS_URL=http://127.0.0.1:5101"
set "OMNIX_STT_URL=http://127.0.0.1:5201"
set "OMNIX_GATEWAY_URL=http://127.0.0.1:8000"
set "OMNIX_LAUNCHER_URL=http://127.0.0.1:5055"
if not defined OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS set "OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS=45"
if not defined OMNIX_APP_OPEN_URL set "OMNIX_APP_OPEN_URL=http://localhost:5173/"
if not defined OMNIX_POSTGRES_CONTAINER set "OMNIX_POSTGRES_CONTAINER=omnix-postgres"
if not defined OMNIX_POSTGRES_START_WAIT_ATTEMPTS set "OMNIX_POSTGRES_START_WAIT_ATTEMPTS=30"
if not defined OMNIX_LAUNCHER_AUTO_START set "OMNIX_LAUNCHER_AUTO_START=1"
if not defined OMNIX_LAUNCHER_OPEN_BROWSER set "OMNIX_LAUNCHER_OPEN_BROWSER=1"
if not defined OMNIX_BLOB_ROOT for %%I in ("%~dp0..\omnix-runtime\blobs") do set "OMNIX_BLOB_ROOT=%%~fI"

call :ensure_postgres
if errorlevel 1 (
    pause
    exit /b 1
)
if /I "%~1"=="--postgres-only" (
    endlocal
    exit /b 0
)
if not defined OMNIX_DATABASE_URL (
    if /I "%~1"=="--database-credential-injected" (
        echo ERROR: The protected PostgreSQL credential loader did not inject OMNIX_DATABASE_URL.
        exit /b 1
    )
    echo [POSTGRES] Loading the current-user protected database credential...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage_postgresql_credential.ps1" -Action launch -BatchPath "%~f0"
    set "OMNIX_CREDENTIAL_LAUNCH_EXIT=!ERRORLEVEL!"
    endlocal & exit /b !OMNIX_CREDENTIAL_LAUNCH_EXIT!
)

REM Live Agent pilot defaults. Override these before running start_all.bat to disable or tune the pilot.
if not defined HERMES_ENABLED set "HERMES_ENABLED=1"
if not defined HERMES_BASE_URL set "HERMES_BASE_URL=http://127.0.0.1:8642"
if not defined OMNIX_START_HERMES set "OMNIX_START_HERMES=1"
if not defined OMNIX_LIVE_AGENT_ENABLED set "OMNIX_LIVE_AGENT_ENABLED=1"
if not defined OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED set "OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=1"
if not defined OMNIX_LIVE_AGENT_REQUIRE_HERMES set "OMNIX_LIVE_AGENT_REQUIRE_HERMES=1"
if not defined OMNIX_LIVE_AGENT_TIMEOUT_SECONDS set "OMNIX_LIVE_AGENT_TIMEOUT_SECONDS=6"
if not defined OMNIX_CHARACTER_MODE_ENABLED set "OMNIX_CHARACTER_MODE_ENABLED=1"

REM Local TP-Link Kasa smart-plug defaults. Host and alias are optional when only one device is discovered.
if not defined OMNIX_KASA_ENABLED set "OMNIX_KASA_ENABLED=1"
if not defined OMNIX_KASA_DISCOVERY_TARGET set "OMNIX_KASA_DISCOVERY_TARGET=255.255.255.255"
if not defined OMNIX_KASA_TIMEOUT_SECONDS set "OMNIX_KASA_TIMEOUT_SECONDS=4"
if not defined OMNIX_KASA_DEVICE_HOST set "OMNIX_KASA_DEVICE_HOST="
if not defined OMNIX_KASA_DEVICE_ALIAS set "OMNIX_KASA_DEVICE_ALIAS="

REM Start the lightweight image service, but keep FLUX.2 [klein] 4B unloaded.
REM The model is loaded and unloaded on demand from the Image Generation page.
REM Override these before running start_all.bat only when intentionally changing behavior.
if not defined OMNIX_IMAGE_ENABLED set "OMNIX_IMAGE_ENABLED=1"
if not defined OMNIX_START_IMAGE_SERVICE set "OMNIX_START_IMAGE_SERVICE=1"
if not defined OMNIX_IMAGE_PRELOAD set "OMNIX_IMAGE_PRELOAD=0"
if not defined OMNIX_IMAGE_WARMUP set "OMNIX_IMAGE_WARMUP=0"
if not defined OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD set "OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD=1"
set "OMNIX_IMAGE_URL="
if /I "%OMNIX_IMAGE_ENABLED%"=="1" if /I "%OMNIX_START_IMAGE_SERVICE%"=="1" set "OMNIX_IMAGE_URL=http://127.0.0.1:5301"

set "OMNIX_TTS_MODELS_DIR=%~dp0resources\models\tts"
set "OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_TTS_MODELS_DIR%\Qwen3-TTS-12Hz-0.6B-Base"
set "OMNIX_TTS_MODEL_DIR="
set "OMNIX_QWEN3_TTS_MODEL_DIR_ENV="

if exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\config.json" if exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\preprocessor_config.json" (
    set "OMNIX_TTS_MODEL_DIR=%OMNIX_QWEN3_TTS_MODEL_DIR%"
    set "OMNIX_QWEN3_TTS_MODEL_DIR_ENV=%OMNIX_QWEN3_TTS_MODEL_DIR%"
)

echo ========================================
echo Omnix Launcher Control
echo ========================================
echo.
echo This starts one launcher dashboard instead of opening separate service terminals.
echo Dashboard: %OMNIX_LAUNCHER_URL%
echo Private app button: %OMNIX_APP_OPEN_URL%
echo API gateway: %OMNIX_GATEWAY_URL%
echo.
echo [LIVE AGENT] Enabled: %OMNIX_LIVE_AGENT_ENABLED%
echo [LIVE AGENT] Automatic routing: %OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED%
echo [LIVE AGENT] Proposal-only Hermes required: %OMNIX_LIVE_AGENT_REQUIRE_HERMES%
echo [LIVE AGENT] Planner timeout: %OMNIX_LIVE_AGENT_TIMEOUT_SECONDS%s
echo [HERMES] Enabled: %HERMES_ENABLED%
echo [HERMES] Base URL: %HERMES_BASE_URL%
echo [HERMES] Auto-start: %OMNIX_START_HERMES%
echo [KASA] Enabled: %OMNIX_KASA_ENABLED%
echo [KASA] Discovery target: %OMNIX_KASA_DISCOVERY_TARGET%
echo [KASA] Device host: %OMNIX_KASA_DEVICE_HOST%
echo [KASA] Device alias: %OMNIX_KASA_DEVICE_ALIAS%
echo [KASA] Timeout: %OMNIX_KASA_TIMEOUT_SECONDS%s
echo.
echo [IMAGE] Service enabled: %OMNIX_IMAGE_ENABLED%
echo [IMAGE] Start lightweight service: %OMNIX_START_IMAGE_SERVICE%
echo [IMAGE] Preload model: %OMNIX_IMAGE_PRELOAD%
echo [IMAGE] Warmup model: %OMNIX_IMAGE_WARMUP%
echo [IMAGE] Explicit load required: %OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD%
if defined OMNIX_IMAGE_URL (
    echo [IMAGE] Service URL: %OMNIX_IMAGE_URL%
    echo [IMAGE] FLUX.2 [klein] 4B will remain unloaded until requested in the web UI.
) else (
    echo [IMAGE] Service disabled for this startup.
)

if not exist "%RPG_FLUX_PYTHON%" (
    echo ERROR: rpg-flux python not found:
    echo   %RPG_FLUX_PYTHON%
    pause
    exit /b 1
)

if not exist "%RPG_TTS_PYTHON%" (
    echo ERROR: rpg-tts python not found:
    echo   %RPG_TTS_PYTHON%
    pause
    exit /b 1
)

if not exist "%RPG_STT_PYTHON%" (
    echo ERROR: rpg-stt python not found:
    echo   %RPG_STT_PYTHON%
    pause
    exit /b 1
)

echo.
echo [ENV CHECK][APP]
"%RPG_FLUX_PYTHON%" -c "import sys; print('[APP][PYTHON]', sys.executable)"
set "PYTHONPATH=%~dp0src"
"%RPG_FLUX_PYTHON%" -c "import fastapi, uvicorn; print('[LAUNCHER] FastAPI/uvicorn OK')"
if errorlevel 1 (
    echo ERROR: launcher environment verification failed
    pause
    exit /b 1
)
echo [POSTGRES] Verifying authoritative database connectivity...
"%RPG_FLUX_PYTHON%" -m app.persistence health
if errorlevel 1 (
    echo ERROR: PostgreSQL connectivity verification failed. Omnix services were not started.
    pause
    exit /b 1
)
if /I "%~1"=="--database-credential-injected-check" (
    endlocal
    exit /b 0
)
if /I "%OMNIX_KASA_ENABLED%"=="1" (
    "%RPG_FLUX_PYTHON%" -c "import kasa; print('[KASA] python-kasa OK')"
    if errorlevel 1 (
        echo WARNING: python-kasa is not installed in rpg-flux.
        echo          Run: "%RPG_FLUX_PYTHON%" -m pip install "python-kasa^>=0.10.2,^<1.0"
    )
)

echo.
echo Starting launcher dashboard in this window...
echo Use Ctrl+C here to stop the launcher itself. Use the dashboard to stop services.
if /I "%OMNIX_LAUNCHER_OPEN_BROWSER%"=="1" (
    echo Opening browser: %OMNIX_LAUNCHER_URL%
    start "" "%OMNIX_LAUNCHER_URL%"
) else (
    echo Browser launch disabled for this startup.
)

set "PYTHONPATH=%~dp0src"
set "OMNIX_TTS_URL=%OMNIX_TTS_URL%"
set "OMNIX_STT_URL=%OMNIX_STT_URL%"
set "OMNIX_GATEWAY_URL=%OMNIX_GATEWAY_URL%"
set "OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS=%OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS%"
set "OMNIX_IMAGE_ENABLED=%OMNIX_IMAGE_ENABLED%"
set "OMNIX_START_IMAGE_SERVICE=%OMNIX_START_IMAGE_SERVICE%"
set "OMNIX_IMAGE_PRELOAD=%OMNIX_IMAGE_PRELOAD%"
set "OMNIX_IMAGE_WARMUP=%OMNIX_IMAGE_WARMUP%"
set "OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD=%OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD%"
set "OMNIX_IMAGE_URL=%OMNIX_IMAGE_URL%"
set "OMNIX_APP_OPEN_URL=%OMNIX_APP_OPEN_URL%"
set "OMNIX_LAUNCHER_AUTO_START=%OMNIX_LAUNCHER_AUTO_START%"
set "OMNIX_LAUNCHER_OPEN_BROWSER=%OMNIX_LAUNCHER_OPEN_BROWSER%"
set "OMNIX_TTS_MODEL_DIR=%OMNIX_TTS_MODEL_DIR%"
set "OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_QWEN3_TTS_MODEL_DIR_ENV%"
set "HERMES_ENABLED=%HERMES_ENABLED%"
set "HERMES_BASE_URL=%HERMES_BASE_URL%"
set "OMNIX_LIVE_AGENT_ENABLED=%OMNIX_LIVE_AGENT_ENABLED%"
set "OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=%OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED%"
set "OMNIX_LIVE_AGENT_REQUIRE_HERMES=%OMNIX_LIVE_AGENT_REQUIRE_HERMES%"
set "OMNIX_LIVE_AGENT_TIMEOUT_SECONDS=%OMNIX_LIVE_AGENT_TIMEOUT_SECONDS%"
set "OMNIX_CHARACTER_MODE_ENABLED=%OMNIX_CHARACTER_MODE_ENABLED%"
set "OMNIX_KASA_ENABLED=%OMNIX_KASA_ENABLED%"
set "OMNIX_KASA_DISCOVERY_TARGET=%OMNIX_KASA_DISCOVERY_TARGET%"
set "OMNIX_KASA_TIMEOUT_SECONDS=%OMNIX_KASA_TIMEOUT_SECONDS%"
set "OMNIX_KASA_DEVICE_HOST=%OMNIX_KASA_DEVICE_HOST%"
set "OMNIX_KASA_DEVICE_ALIAS=%OMNIX_KASA_DEVICE_ALIAS%"
set "KASA_USERNAME=%KASA_USERNAME%"
set "KASA_PASSWORD=%KASA_PASSWORD%"

REM The launcher normally auto-starts the gateway. This watchdog retries that
REM managed service and waits for the API before the web app is used, preventing
REM the Vite proxy from repeatedly receiving ECONNREFUSED on port 8000.
start "Omnix Gateway Startup Check" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$launcher='%OMNIX_LAUNCHER_URL%'; $health='%OMNIX_GATEWAY_URL%/api/health'; $deadline=(Get-Date).AddSeconds(%OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS%); while ((Get-Date) -lt $deadline) { try { $null=Invoke-WebRequest -UseBasicParsing -Uri $launcher -TimeoutSec 2; try { $null=Invoke-RestMethod -Method Post -Uri ($launcher + '/api/services/gateway/start') -TimeoutSec 10 } catch { }; try { $null=Invoke-WebRequest -UseBasicParsing -Uri $health -TimeoutSec 2; Write-Host '[STARTUP] Omnix gateway is ready on port 8000.'; exit 0 } catch { } } catch { }; Start-Sleep -Seconds 1 }; Write-Host '[STARTUP] WARNING: Omnix gateway did not become ready on port 8000.'"

"%RPG_FLUX_PYTHON%" -m uvicorn app.launcher.runtime_control_app:app --host 127.0.0.1 --port 5055 --lifespan on
set "OMNIX_EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %OMNIX_EXIT_CODE%

:ensure_postgres
echo [POSTGRES] Checking Docker and container %OMNIX_POSTGRES_CONTAINER%...
where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker CLI was not found. Install or repair Docker Desktop before starting Omnix.
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Desktop is not running or is not accessible.
    echo        Start Docker Desktop, wait for it to become ready, and try again.
    exit /b 1
)

docker inspect "%OMNIX_POSTGRES_CONTAINER%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PostgreSQL container %OMNIX_POSTGRES_CONTAINER% does not exist.
    echo        Provision it with docker-compose.postgres.yml and operator-owned credentials first.
    exit /b 1
)

set "OMNIX_POSTGRES_RUNNING="
for /f "usebackq delims=" %%S in (`docker inspect --format "{{.State.Running}}" "%OMNIX_POSTGRES_CONTAINER%" 2^>nul`) do set "OMNIX_POSTGRES_RUNNING=%%S"
if /I not "!OMNIX_POSTGRES_RUNNING!"=="true" (
    echo [POSTGRES] Starting existing container %OMNIX_POSTGRES_CONTAINER%...
    docker start "%OMNIX_POSTGRES_CONTAINER%" >nul
    if errorlevel 1 (
        echo ERROR: Failed to start PostgreSQL container %OMNIX_POSTGRES_CONTAINER%.
        exit /b 1
    )
) else (
    echo [POSTGRES] Container is already running.
)

echo [POSTGRES] Waiting for the database health check...
for /L %%I in (1,1,%OMNIX_POSTGRES_START_WAIT_ATTEMPTS%) do (
    set "OMNIX_POSTGRES_HEALTH="
    for /f "usebackq delims=" %%H in (`docker inspect --format "{{.State.Health.Status}}" "%OMNIX_POSTGRES_CONTAINER%" 2^>nul`) do set "OMNIX_POSTGRES_HEALTH=%%H"
    if /I "!OMNIX_POSTGRES_HEALTH!"=="healthy" (
        echo [POSTGRES] Database is healthy.
        exit /b 0
    )
    timeout /t 2 /nobreak >nul
)

echo ERROR: PostgreSQL container %OMNIX_POSTGRES_CONTAINER% did not become healthy.
docker ps --filter "name=%OMNIX_POSTGRES_CONTAINER%" --format "table {{.Names}}\t{{.Status}}"
exit /b 1
