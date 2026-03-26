@echo off
REM ============================================
REM Omnix - Setup Script (Windows) with Virtual Environment
REM ============================================

echo =============================================
echo Omnix - Setup with Virtual Environment
echo =============================================
echo.
echo This will install all dependencies for:
echo   - Chatbot Web Server
echo   - Parakeet STT (Speech-to-Text)
echo   - FasterQwen3TTS (Text-to-Speech)
echo.
echo Using Python virtual environment for isolation
pause

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10 or higher from https://www.python.org/
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo Python version: %PYVER%

echo.
echo [1/7] Creating Python virtual environment...
if exist "venv" (
    echo Virtual environment already exists, removing...
    rmdir /s /q venv
)

python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat
echo Virtual environment activated

echo.
echo [2/7] Upgrading pip...
pip install --upgrade pip

echo.
echo [3/7] Installing PyTorch with CUDA 12.4 support...
echo This is CRITICAL - mismatched versions cause errors
echo.
pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo WARNING: Failed to install PyTorch with CUDA
    echo Trying CPU-only version...
    pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
)

echo.
echo [4/7] Installing torchmetrics...
pip install torchmetrics==1.4.2

echo.
echo [5/7] Installing core dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install core dependencies
    pause
    exit /b 1
)

echo.
echo [6/8] Installing FasterQwen3TTS...
pip install faster-qwen3-tts>=0.2.4
if errorlevel 1 (
    echo WARNING: Failed to install FasterQwen3TTS
    echo You can try: pip install faster-qwen3-tts
)

echo.
echo [7/7] Installing NeMo ASR for Parakeet STT...
pip install "nemo_toolkit[asr]"
if errorlevel 1 (
    echo WARNING: Failed to install NeMo ASR
    echo STT will not be available
    echo Try: pip install nemo_toolkit[asr]
)

echo.
echo [8/8] Installing compatible transformers version...
echo Note: nemo_toolkit installs transformers 4.53+ which may break compatibility
echo Installing transformers==4.46.3 for better compatibility...
pip install transformers==4.46.3 tokenizers==0.20.3 --force-reinstall

echo.
echo [9/9] Pre-downloading Parakeet TDT 0.6B model...
echo This may take a few minutes...
echo Note: Model downloads to HuggingFace cache: %USERPROFILE%\.cache\huggingface\
python -c "from nemo.collections.asr.models import ASRModel; ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); print('Parakeet model downloaded successfully!')" 2>nul
if errorlevel 1 (
    echo WARNING: Failed to pre-download Parakeet model
    echo It will be downloaded on first use instead
)

echo.
echo [10/10] Downloading default LLM (Qwen3-4B Q8_0)...
echo This provides an immediate working LLM for new installations
echo Model: qwen/Qwen3-4B-Instruct-2507-GGUF
echo Quantization: Q8_0 (~4GB)
echo.

REM Create models directory
if not exist "models\llm" mkdir "models\llm"

REM Download using huggingface-cli or curl
echo Downloading Qwen3-4B GGUF model...
python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='qwen/Qwen3-4B-Instruct-2507-GGUF', filename='qwen3-4b-instruct-2507-q8_0.gguf', local_dir='models/llm', local_dir_use_symlinks=False)" 2>nul
if errorlevel 1 (
    echo Could not auto-download - will provide manual instructions below
) else (
    echo Qwen3-4B model downloaded to models/llm/
)

echo.
echo [11/11] Verifying installations...
echo.

REM Check PyTorch
python -c "import torch; print(f'PyTorch: {torch.__version__}')" 2>nul
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')" 2>nul

REM Check TTS
python -c "import faster_qwen3_tts; print('FasterQwen3TTS: OK')" 2>nul
if errorlevel 1 (
    echo FasterQwen3TTS: FAILED - check faster-qwen3-tts installation
)

REM Check STT
python -c "import nemo.collections.asr as nemo_asr; print('NeMo ASR: OK')" 2>nul
if errorlevel 1 (
    echo NeMo ASR: FAILED - check nemo_toolkit installation
)

echo.
echo =============================================
echo Setup Complete!
echo =============================================
echo.
echo IMPORTANT NOTES:
echo   - Virtual environment created in 'venv' directory
echo   - To activate: venv\Scripts\activate.bat
echo   - To deactivate: deactivate
echo   - PyTorch must match torchvision version
echo   - Use parakeet_stt_server.py from root (not models folder)
echo   - transformers will be updated to 4.53.x by nemo_toolkit
echo.
echo To start services:
echo   start_all.bat             - Start all services
echo   start_parakeet_stt.bat    - Start STT only
echo.
echo To run with virtual environment:
echo   venv\Scripts\activate.bat && start_all.bat
echo.
pause
