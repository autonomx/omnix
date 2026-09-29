@echo off
setlocal
set "OMNIX_REPO_ROOT=%~dp0.."
for %%I in ("%OMNIX_REPO_ROOT%") do set "OMNIX_REPO_ROOT=%%~fI"
cd /d "%OMNIX_REPO_ROOT%"

echo Starting OpenAI Compatible API Server...
echo =========================================

REM Check if Python 3.11 is installed
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.11 is not installed. Please install Python 3.11 first.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist venv (
    echo Creating virtual environment...
    py -3.11 -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate

REM Install requirements if needed
echo Installing/updating requirements...
python -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
if errorlevel 1 (
    echo The existing venv must use Python 3.11. Remove it and rerun this launcher.
    exit /b 1
)
python -m pip install --require-hashes -r requirements.txt

REM Start the OpenAI API server
echo Starting OpenAI Compatible API Server on port 8101 by default...
echo Access the API at: http://localhost:8101
echo API endpoints:
echo   - /v1/models (list models)
echo   - /v1/audio/voices (list voices)
echo   - /v1/audio/speech (generate speech)
echo   - /v1/chat/completions (chat completions)
echo   - /health (health check)
echo.
echo Press Ctrl+C to stop the server
echo =========================================

python src\openai_api.py

pause
endlocal
