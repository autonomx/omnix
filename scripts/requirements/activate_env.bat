@echo off
REM ============================================
REM Omnix - Virtual Environment Activation Script (Windows)
REM ============================================

echo =============================================
echo Omnix - Virtual Environment Activation
echo =============================================
echo.

REM Resolve the repository root so this helper can live under scripts\requirements\.
set "OMNIX_REPO_ROOT=%~dp0..\.."
for %%I in ("%OMNIX_REPO_ROOT%") do set "OMNIX_REPO_ROOT=%%~fI"
cd /d "%OMNIX_REPO_ROOT%"

REM Check if virtual environment exists
if exist "venv" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
    echo Virtual environment activated!
    echo You can now run: python app.py
    echo To deactivate: deactivate
    echo.
    echo Starting command prompt with virtual environment...
    cmd.exe
) else (
    echo ERROR: Virtual environment not found!
    echo Please run: setup.bat
    echo Then try again.
    pause
    exit /b 1
)
