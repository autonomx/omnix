@echo off

:: Disable HuggingFace internet checks when model is already local
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set HF_DATASETS_OFFLINE=1
set HF_EVALUATE_OFFLINE=1

echo ================================================
echo FasterQwen3TTS Model Setup
echo ================================================
echo.
echo This script will:
echo   1. Install FasterQwen3TTS dependencies
echo   2. Download the model (if needed)
echo   3. Test the integration
echo   4. Start the chatbot with FasterQwen3TTS
echo.
echo Note: First run will download the model (~1-2GB)
echo       Subsequent runs will be much faster
echo.

cd /d "%~dp0"

:: Check if virtual environment exists and activate it
if exist "venv" (
    echo [Setup] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found. You may need to run setup.bat first.
    echo Continuing without virtual environment...
)

:: Install FasterQwen3TTS dependencies
echo [1/4] Installing FasterQwen3TTS dependencies...
pip install -q faster-qwen3-tts qwen-tts soundfile numpy scipy librosa

if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    echo Please check your internet connection and try again
    pause
    exit /b 1
)

echo ✓ Dependencies installed successfully

:: Run setup script
echo [2/4] Running FasterQwen3TTS setup...
python setup_faster_qwen3_tts.py

if %errorlevel% neq 0 (
    echo ERROR: Setup failed
    pause
    exit /b 1
)

echo ✓ Setup completed

:: Test the integration
echo [3/4] Testing FasterQwen3TTS integration...
python test_faster_qwen3_tts.py

if %errorlevel% neq 0 (
    echo WARNING: Some tests failed, but continuing...
) else (
    echo ✓ All tests passed
)

:: Start the chatbot
echo [4/4] Starting chatbot with FasterQwen3TTS...
echo.
echo ================================================
echo Starting Chatbot with FasterQwen3TTS
echo ================================================
echo.
echo The chatbot will use FasterQwen3TTS as the default TTS provider.
echo.
echo Features available:
echo   - Real-time TTS with 6-10x speedup
echo   - Voice cloning from audio files
echo   - Multilingual support
echo   - Custom voice management
echo.
echo Access the web interface at: http://localhost:5000
echo.
echo Note: The model will load automatically on first TTS request.
echo       This may take 1-2 minutes on the first run.
echo.

python app.py

echo.
echo Server closed. Press any key to exit...
pause