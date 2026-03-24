@echo off
echo ================================================
echo LM Studio Chatbot - Full Launcher
echo ================================================
echo.
echo This will start:
echo   1. Parakeet STT Server (port 8000) - Voice recognition
echo   2. FasterQwen3TTS Model - Real-time multilingual TTS
echo   3. Chatbot Web Server (port 5000) - Main application
echo.

set SERVER_MODE=fastapi
echo Starting in %SERVER_MODE% mode...
echo.

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
)

echo [Setup] Installing dependencies...
pip install -q fastapi uvicorn websockets aiohttp pydub numpy soundfile 2>nul

set PARKEET_FORCE_CPU=false

echo [1/3] Starting Parakeet STT Server...
start "Parakeet STT" cmd /k "cd /d "%~dp0" && set PARKEET_FORCE_CPU=false && python parakeet_stt_server.py 2>&1"

echo Waiting for STT...
ping -n 6 127.0.0.1 >nul

echo [2/3] Starting Chatbot...
if "%SERVER_MODE%"=="fastapi" (
    start "Omnix FastAPI" cmd /k "cd /d "%~dp0" && python server_fastapi.py 2>&1"
) else (
    start "Omnix Flask" cmd /k "cd /d "%~dp0" && python app.py 2>&1"
)

echo.
echo All servers started!
pause
