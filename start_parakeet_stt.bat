@echo off
setlocal

set "RPG_STT_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-stt\python.exe"
set "STT_SERVER=%~dp0src\parakeet_stt_server.py"

if not exist "%RPG_STT_PYTHON%" (
    echo ERROR: rpg-stt python not found:
    echo   %RPG_STT_PYTHON%
    pause
    exit /b 1
)

if not exist "%STT_SERVER%" (
    echo ERROR: Parakeet STT server not found:
    echo   %STT_SERVER%
    pause
    exit /b 1
)

echo Starting Parakeet TDT STT Server...
echo Python: %RPG_STT_PYTHON%
echo Server: %STT_SERVER%
echo WebSocket: ws://127.0.0.1:5201/ws/transcribe
echo.

"%RPG_STT_PYTHON%" -c "import fastapi, uvicorn, websockets, nemo.collections.asr; print('[STT] dependencies OK')"
if errorlevel 1 (
    echo.
    echo ERROR: The rpg-stt environment is missing a required dependency.
    echo Install WebSocket support with:
    echo   "%RPG_STT_PYTHON%" -m pip install "uvicorn[standard]"
    pause
    exit /b 1
)

set "OMNIX_STT_PORT=5201"
"%RPG_STT_PYTHON%" "%STT_SERVER%"

endlocal
