@echo off
setlocal EnableDelayedExpansion

set "RPG_FLUX_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-flux\python.exe"
set "RPG_TTS_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-tts\python.exe"
set "RPG_STT_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-stt\python.exe"

set "OMNIX_TTS_URL=http://127.0.0.1:5101"
set "OMNIX_STT_URL=http://127.0.0.1:5201"
set "OMNIX_IMAGE_URL=http://127.0.0.1:5301"

set "OMNIX_TTS_MODELS_DIR=%~dp0resources\models\tts"
set "OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_TTS_MODELS_DIR%\Qwen3-TTS-12Hz-0.6B-Base"

set "OMNIX_TTS_MODEL_DIR="
set "OMNIX_QWEN3_TTS_MODEL_DIR_ENV="

if exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\config.json" if exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\preprocessor_config.json" (
    set "OMNIX_TTS_MODEL_DIR=%OMNIX_QWEN3_TTS_MODEL_DIR%"
    set "OMNIX_QWEN3_TTS_MODEL_DIR_ENV=%OMNIX_QWEN3_TTS_MODEL_DIR%"
    echo [TTS] Using local downloaded model:
    echo        %OMNIX_QWEN3_TTS_MODEL_DIR%
) else (
    echo [TTS][WARN] Local Qwen3-TTS model not found:
    echo        %OMNIX_QWEN3_TTS_MODEL_DIR%
    echo [TTS] Run setup first.
)

echo ========================================
echo Starting Omnix with split runtime envs
echo ========================================

if defined OMNIX_TTS_MODEL_DIR (
    echo [TTS] Using cached HF snapshot:
    echo        !OMNIX_TTS_MODEL_DIR!
) else (
    echo [TTS] No cached HF snapshot found. Provider will use repo id/download path.
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
echo [ENV CHECK][FLUX]
"%RPG_FLUX_PYTHON%" -c "import sys; print('[FLUX][PYTHON]', sys.executable)"
"%RPG_FLUX_PYTHON%" -c "import diffusers; print('[FLUX] diffusers OK')"
set "PYTHONPATH=%~dp0src"
"%RPG_FLUX_PYTHON%" -c "from app.providers.vendor.qwen3_tts.bootstrap import ensure_vendored_qwen3_tts_available; print('[FLUX][TTS][VENDORED]', ensure_vendored_qwen3_tts_available())"
if errorlevel 1 (
    echo ERROR: rpg-flux verification failed
    pause
    exit /b 1
)

echo.
echo [IMAGE SERVICE] Starting image service on %OMNIX_IMAGE_URL%...
start "Omnix Image Service" cmd /k "cd /d ""%~dp0"" && set ""PYTHONPATH=%~dp0src"" && set ""OMNIX_IMAGE_SERVICE_MODE=1"" && set ""OMNIX_IMAGE_URL="" && ""%RPG_FLUX_PYTHON%"" -m uvicorn app.image_service_app:app --host 127.0.0.1 --port 5301 2>&1"

echo Waiting for image service...
ping -n 4 127.0.0.1 >nul

echo.
echo [ENV CHECK][TTS]
"%RPG_TTS_PYTHON%" -c "import sys; print('[TTS][PYTHON]', sys.executable)"
if errorlevel 1 (
    echo ERROR: rpg-tts verification failed
    pause
    exit /b 1
)

if not exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\config.json" (
    echo ERROR: Qwen3-TTS model missing:
    echo   %OMNIX_QWEN3_TTS_MODEL_DIR%
    echo Run setup first.
    pause
    exit /b 1
)

echo.
echo [ENV CHECK][STT]
"%RPG_STT_PYTHON%" -c "import sys; print('[STT][PYTHON]', sys.executable)"
"%RPG_STT_PYTHON%" -c "import nemo.collections.asr as nemo_asr; print('[STT] NeMo ASR OK')"
if errorlevel 1 (
    echo ERROR: rpg-stt verification failed
    pause
    exit /b 1
)

echo [STT] Verifying websocket support...
"%RPG_STT_PYTHON%" -c "import websockets; print('[STT] websockets OK')"
if errorlevel 1 (
    echo [STT] websockets missing, installing...
    "%RPG_STT_PYTHON%" -m pip install websockets
    if errorlevel 1 (
        echo ERROR: failed to install websockets into rpg-stt
        pause
        exit /b 1
    )
)

echo.
echo ================================================
echo LM Studio Chatbot - Full Launcher
echo ================================================
echo.

echo [1/4] Starting Parakeet STT...
start "Parakeet STT" cmd /k "cd /d ""%~dp0"" && ""%RPG_STT_PYTHON%"" -c "import sys; print('[STT][PYTHON]', sys.executable)" && ""%RPG_STT_PYTHON%"" src\parakeet_stt_server.py"

echo Waiting for STT...
ping -n 6 127.0.0.1 >nul



echo.
echo [2/4] Starting TTS...
start "Omnix TTS" cmd /k "cd /d ""%~dp0"" && set ""PYTHONPATH=%~dp0src"" && set ""OMNIX_TTS_MODEL_DIR=%OMNIX_TTS_MODEL_DIR%"" && set ""OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_QWEN3_TTS_MODEL_DIR_ENV%"" && ""%RPG_TTS_PYTHON%"" src\tts_server.py 2>&1"

echo Waiting for TTS...
ping -n 4 127.0.0.1 >nul

echo.
echo [3/4] Starting Chatbot...
start "Omnix FastAPI" cmd /k "cd /d ""%~dp0"" && set ""PYTHONPATH=%~dp0src"" && set ""OMNIX_TTS_URL=%OMNIX_TTS_URL%"" && set ""OMNIX_STT_URL=%OMNIX_STT_URL%"" && set ""OMNIX_IMAGE_URL=%OMNIX_IMAGE_URL%"" && set ""OMNIX_TTS_MODEL_DIR=%OMNIX_TTS_MODEL_DIR%"" && set ""OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_QWEN3_TTS_MODEL_DIR_ENV%"" && ""%RPG_FLUX_PYTHON%"" -c "import sys; print('[APP][PYTHON]', sys.executable)" && ""%RPG_FLUX_PYTHON%"" -c "import diffusers; print('[APP][FLUX] diffusers OK')" && ""%RPG_FLUX_PYTHON%"" src\launch.py 2>&1"

echo Waiting for FastAPI...
ping -n 4 127.0.0.1 >nul

echo.
echo [4/4] Services launched.
echo.
echo STT window should show:
echo   [STT][PYTHON] C:\Users\unx47\miniconda3\envs\rpg-stt\python.exe
echo.
echo App window should show:
echo   [APP][PYTHON] C:\Users\unx47\miniconda3\envs\rpg-flux\python.exe
echo   [APP][FLUX] diffusers OK
echo   [APP][TTS][VENDORED] vendored path loaded OK
echo.
echo All servers started!
pause
endlocal