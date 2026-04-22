@echo off
echo ########################################
echo ### USING SETUP.BAT (CURRENT VERSION) ###
echo ########################################
pause
setlocal
set "OMNIX_REPO_ROOT=%~dp0"
set "OMNIX_REPO_ROOT=%OMNIX_REPO_ROOT:~0,-1%"

REM ============================================
REM Omnix - Split Runtime Setup Script (Windows)
REM ============================================

set "CONDA_ROOT=C:\Users\unx47\miniconda3"
set "CONDA_EXE=%CONDA_ROOT%\Scripts\conda.exe"

set "RPG_FLUX_ENV=rpg-flux"
set "RPG_FLUX_PYTHON=%CONDA_ROOT%\envs\rpg-flux\python.exe"

set "RPG_TTS_ENV=rpg-tts"
set "RPG_TTS_PYTHON=%CONDA_ROOT%\envs\rpg-tts\python.exe"

set "RPG_STT_ENV=rpg-stt"
set "RPG_STT_PYTHON=%CONDA_ROOT%\envs\rpg-stt\python.exe"

set "OMNIX_MODELS_ROOT=%OMNIX_REPO_ROOT%\resources\models"
set "OMNIX_LLM_MODELS_DIR=%OMNIX_MODELS_ROOT%\llm"
set "OMNIX_TTS_MODELS_DIR=%OMNIX_MODELS_ROOT%\tts"
set "OMNIX_STT_MODELS_DIR=%OMNIX_MODELS_ROOT%\stt"
set "OMNIX_IMAGE_MODELS_DIR=%OMNIX_MODELS_ROOT%\image"

set "OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_TTS_MODELS_DIR%\Qwen3-TTS-12Hz-0.6B-Base"
set "OMNIX_QWEN3_TTS_REPO_ID=Qwen/Qwen3-TTS-12Hz-0.6B-Base"

echo =============================================
echo Omnix - Setup with Split Conda Environments
echo =============================================
echo.
echo This will install all dependencies for:
echo   - Main app + FLUX image generation in %RPG_FLUX_ENV%
echo   - Vendored Qwen3-TTS in %RPG_TTS_ENV%
echo   - Parakeet STT in %RPG_STT_ENV%
echo.
echo Setup will start automatically in 3 seconds...
ping 127.0.0.1 -n 3 -w 1000 >nul

if not exist "%CONDA_EXE%" (
    echo ERROR: conda.exe not found:
    echo   %CONDA_EXE%
    pause
    exit /b 1
)

if not exist "%RPG_FLUX_PYTHON%" (
    echo Creating conda environment: %RPG_FLUX_ENV%
    "%CONDA_EXE%" create -n %RPG_FLUX_ENV% python=3.10 -y
    if errorlevel 1 (
        echo ERROR: Failed to create %RPG_FLUX_ENV%
        pause
        exit /b 1
    )
)

if not exist "%RPG_TTS_PYTHON%" (
    echo Creating conda environment: %RPG_TTS_ENV%
    "%CONDA_EXE%" create -n %RPG_TTS_ENV% python=3.10 -y
    if errorlevel 1 (
        echo ERROR: Failed to create %RPG_TTS_ENV%
        pause
        exit /b 1
    )
)

if not exist "%RPG_STT_PYTHON%" (
    echo Creating conda environment: %RPG_STT_ENV%
    "%CONDA_EXE%" create -n %RPG_STT_ENV% python=3.10 -y
    if errorlevel 1 (
        echo ERROR: Failed to create %RPG_STT_ENV%
        pause
        exit /b 1
    )
)

if not exist "src\requirements-rpg-flux.txt" (
    echo ERROR: Runtime requirements file not found
    echo Expected:
    echo   src\requirements-rpg-flux.txt
    pause
    exit /b 1
)

if not exist "src\requirements-rpg-tts.txt" (
    echo ERROR: TTS runtime requirements file not found
    echo Expected:
    echo   src\requirements-rpg-tts.txt
    pause
    exit /b 1
)

echo.
echo [ENV CHECK] FLUX
"%RPG_FLUX_PYTHON%" -c "import sys; print('FLUX Python:', sys.executable)"
if errorlevel 1 (
    echo ERROR: Failed to verify %RPG_FLUX_ENV%
    pause
    exit /b 1
)

echo.
echo [ENV CHECK] STT
"%RPG_STT_PYTHON%" -c "import sys; print('STT Python:', sys.executable)"
if errorlevel 1 (
    echo ERROR: Failed to verify %RPG_STT_ENV%
    pause
    exit /b 1
)

echo.
echo =============================================
echo Installing main app + FLUX into %RPG_FLUX_ENV%
echo =============================================

if not exist "src\app\providers\vendor\faster_qwen3_tts\__init__.py" (
    echo ERROR: Vendored faster_qwen3_tts package not found
    echo Expected:
    echo   src\app\providers\vendor\faster_qwen3_tts\__init__.py
    pause
    exit /b 1
)

if not exist "src\app\providers\vendor\qwen_tts\__init__.py" (
    echo ERROR: Vendored qwen_tts package not found
    echo Expected:
    echo   src\app\providers\vendor\qwen_tts\__init__.py
    pause
    exit /b 1
)

echo [1/9][FLUX] Upgrading pip/setuptools/wheel...
"%RPG_FLUX_PYTHON%" -m pip install --upgrade pip

REM Pin wheel to avoid packaging>=24 requirement (deepfilternet requires <24)
"%RPG_FLUX_PYTHON%" -m pip install wheel==0.43.0
if errorlevel 1 (
    echo ERROR: Failed to pin wheel
    pause
    exit /b 1
)

REM DO NOT upgrade setuptools/packaging here — breaks deepfilternet + torch constraints

echo.
echo [2/9][FLUX] Removing conflicting torch packages...
"%RPG_FLUX_PYTHON%" -m pip uninstall -y torch torchvision torchaudio
"%RPG_FLUX_PYTHON%" -m pip uninstall -y torchtext torchdata

echo.
echo [3/9][FLUX] Installing torch/vision/audio CUDA 12.4 trio...
"%RPG_FLUX_PYTHON%" -m pip install --no-cache-dir --force-reinstall torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 numpy==1.26.4 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo WARNING: CUDA trio failed for %RPG_FLUX_ENV%, falling back to CPU
    "%RPG_FLUX_PYTHON%" -m pip install --no-cache-dir --force-reinstall torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 numpy==1.26.4
    if errorlevel 1 (
        echo ERROR: Failed to install torch trio into %RPG_FLUX_ENV%
        pause
        exit /b 1
    )
)

echo.
echo [FLUX] Cleaning conflicting pip-installed TTS packages...

REM These packages conflict with the vendored Qwen3-TTS runtime and can
REM force incompatible transformers/accelerate versions into the env.
REM We explicitly remove them to guarantee a clean deterministic runtime.

"%RPG_FLUX_PYTHON%" -m pip uninstall -y faster-qwen3-tts >nul 2>nul
if errorlevel 0 (
    echo   removed faster-qwen3-tts
) else (
    echo   faster-qwen3-tts not present
)

"%RPG_FLUX_PYTHON%" -m pip uninstall -y qwen-tts >nul 2>nul
if errorlevel 0 (
    echo   removed qwen-tts
) else (
    echo   qwen-tts not present
)

REM Optional: clear HF cache metadata for these packages (safe no-op if not present)
REM Uncomment if you see persistent version bleed-through issues
REM rmdir /s /q "%USERPROFILE%\.cache\huggingface\modules\transformers_modules" 2>nul

echo [FLUX] Cleanup complete.

echo.
echo [4/9][FLUX] Installing main app requirements (excluding HF/FLUX stack)...
"%RPG_FLUX_PYTHON%" -m pip install -r requirements-rpg-main-nohf.txt
if errorlevel 1 goto :error


echo.
echo [5/9][FLUX] Installing centralized RPG-FLUX runtime requirements...
"%RPG_FLUX_PYTHON%" -m pip install -r src\requirements-rpg-flux.txt
if errorlevel 1 goto :error

echo.
echo [6/9][FLUX] TTS moved to dedicated %RPG_TTS_ENV% environment

echo.
echo [7/9][FLUX] Runtime dependency pins are managed by src\requirements-rpg-flux.txt

echo.
echo [8/9][FLUX] Downloading default LLM (Qwen3-4B Q8_0)...
if not exist "%OMNIX_LLM_MODELS_DIR%" mkdir "%OMNIX_LLM_MODELS_DIR%"
"%RPG_FLUX_PYTHON%" -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='qwen/Qwen3-4B-Instruct-2507-GGUF', filename='qwen3-4b-instruct-2507-q8_0.gguf', local_dir=r'%OMNIX_LLM_MODELS_DIR%', local_dir_use_symlinks=False)" 2>nul
if errorlevel 1 (
    echo WARNING: Could not auto-download Qwen3-4B GGUF model
) else (
    echo Qwen3-4B model downloaded to %OMNIX_LLM_MODELS_DIR%/
)

echo.
echo [9/9][FLUX] Verifying main app runtime...
set PYTHONPATH=%CD%\src
"%RPG_FLUX_PYTHON%" -c "import torch, torchvision, torchaudio; print('torch:', torch.__version__); print('torchvision:', torchvision.__version__); print('torchaudio:', torchaudio.__version__)"
"%RPG_FLUX_PYTHON%" -c "import torch; print('torch:', torch.__version__)"
if errorlevel 1 goto :error
"%RPG_FLUX_PYTHON%" -c "import torchvision; print('torchvision:', torchvision.__version__)"
if errorlevel 1 goto :error
"%RPG_FLUX_PYTHON%" -c "import diffusers; print('diffusers OK')"
if errorlevel 1 goto :error
"%RPG_FLUX_PYTHON%" -c "from app.rpg.visual.runtime_status import validate_flux_klein_runtime; s=validate_flux_klein_runtime(); print('FLUX:', 'READY' if s.get('ready') else 'NOT READY', s.get('error','')); raise SystemExit(0 if s.get('ready') else 1)"
if errorlevel 1 goto :error
echo [FLUX] Runtime verification complete.
echo =============================================
echo FLUX: READY
echo =============================================

echo.
echo =============================================
echo Installing dedicated TTS service into %RPG_TTS_ENV%
echo =============================================

echo.
echo [1/5][TTS] Upgrading pip/setuptools/wheel...
"%RPG_TTS_PYTHON%" -m pip install --upgrade pip wheel==0.43.0 setuptools==81.0.0
if errorlevel 1 goto :error

echo.
echo [2/5][TTS] Installing dedicated TTS requirements...
"%RPG_TTS_PYTHON%" -m pip install --force-reinstall -r src\requirements-rpg-tts.txt
if errorlevel 1 goto :error

echo.
echo =============================================
echo Downloading Qwen3-TTS model
echo =============================================

call "%OMNIX_REPO_ROOT%\download_tts_only.bat"
if errorlevel 1 goto :error

echo.
echo [VERIFY][TTS MODEL] Checking local Qwen3-TTS files...
"%RPG_TTS_PYTHON%" -c "from pathlib import Path; p=Path(r'%OMNIX_QWEN3_TTS_MODEL_DIR%'); shards=list(p.glob('*.safetensors')); print('model_dir:', p); print('safetensors_shards:', [s.name for s in shards]); assert (p/'config.json').exists(), 'Missing config.json'; assert (p/'preprocessor_config.json').exists(), 'Missing preprocessor_config.json'; assert shards, 'No safetensors shards found'"
if errorlevel 1 goto :error

echo.
echo [SMOKE][TTS MODEL] Attempting real local from_pretrained load...
"%RPG_TTS_PYTHON%" -c "import sys; sys.path.insert(0, r'%OMNIX_REPO_ROOT%\src'); from app.providers.vendor.qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel; model_dir=r'%OMNIX_QWEN3_TTS_MODEL_DIR%'; print('Loading from:', model_dir); model = Qwen3TTSModel.from_pretrained(model_dir); print('Qwen3TTSModel local load OK:', type(model).__name__)"
if errorlevel 1 goto :error

echo.
echo [VERIFY][TTS] transformers/tokenizers/onnxruntime versions.
"%RPG_TTS_PYTHON%" -c "import transformers, tokenizers, onnxruntime; print('transformers:', transformers.__version__); print('tokenizers:', tokenizers.__version__); print('onnxruntime:', onnxruntime.__version__)"
if errorlevel 1 goto :error

echo.
echo [3/5][TTS] Verifying tts_server import...
"%RPG_TTS_PYTHON%" -c "import sys; sys.path.insert(0, r'%OMNIX_REPO_ROOT%\src'); import tts_server; print('tts_server import OK')"
if errorlevel 1 goto :error

echo.
echo [4/5][TTS] Verifying HTTP TTS contract boot path...
"%RPG_TTS_PYTHON%" -c "import sys; sys.path.insert(0, r'%OMNIX_REPO_ROOT%\src'); import tts_server; app = tts_server.app; print('tts_server app OK')"
if errorlevel 1 goto :error

echo.
echo [5/5][TTS] Verifying provider status helper...
"%RPG_TTS_PYTHON%" -c "import sys; sys.path.insert(0, r'%OMNIX_REPO_ROOT%\src'); import tts_server; s = tts_server.get_tts_service_status(); print('TTS:', 'READY' if s.get('ok') else 'NOT READY', s.get('error',''))"
if errorlevel 1 goto :error

echo [TTS] Runtime verification complete.

echo.
echo =============================================
echo Installing Parakeet STT into %RPG_STT_ENV%
echo =============================================

echo [1/7][STT] Upgrading pip/setuptools/wheel...
"%RPG_STT_PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip tools in %RPG_STT_ENV%
    pause
    exit /b 1
)

echo.
echo [2/7][STT] Removing conflicting torch packages...
"%RPG_STT_PYTHON%" -m pip uninstall -y torch torchvision torchaudio

echo.
echo [3/7][STT] Installing torch 2.6+ for NeMo compatibility...
"%RPG_STT_PYTHON%" -m pip install --no-cache-dir torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo WARNING: CUDA trio failed for %RPG_STT_ENV%, falling back to CPU
    "%RPG_STT_PYTHON%" -m pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0
    if errorlevel 1 (
        echo ERROR: Failed to install torch trio into %RPG_STT_ENV%
        pause
        exit /b 1
    )
)

echo.
echo [4/7][STT] Installing NeMo ASR...
"%RPG_STT_PYTHON%" -m pip install "nemo_toolkit[asr]"
if errorlevel 1 (
    echo ERROR: Failed to install nemo_toolkit[asr]
    pause
    exit /b 1
)

echo.
echo [STT] Installing web server dependencies for parakeet_stt_server...
"%RPG_STT_PYTHON%" -m pip install fastapi uvicorn python-multipart
if errorlevel 1 (
    echo ERROR: Failed to install FastAPI/Uvicorn/python-multipart in %RPG_STT_ENV%
    pause
    exit /b 1
)

echo.
echo [5/7][STT] Reinstalling exact torch/vision/audio trio after NeMo...
"%RPG_STT_PYTHON%" -m pip install --no-cache-dir --force-reinstall torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo WARNING: CUDA trio reinstall failed for %RPG_STT_ENV%, falling back to CPU
    "%RPG_STT_PYTHON%" -m pip install --no-cache-dir --force-reinstall torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0
    if errorlevel 1 (
        echo ERROR: Failed to reassert torch trio in %RPG_STT_ENV%
        pause
        exit /b 1
    )
)

echo.
echo [6/7][STT] Installing STT transformers/tokenizers compatibility pins...
"%RPG_STT_PYTHON%" -m pip install transformers==4.46.3 tokenizers==0.20.3 --force-reinstall
if errorlevel 1 (
    echo ERROR: Failed to install STT transformers/tokenizers compatibility pins
    pause
    exit /b 1
)

echo.
echo [7/7][STT] Pre-downloading Parakeet model...
if not exist "%OMNIX_STT_MODELS_DIR%" mkdir "%OMNIX_STT_MODELS_DIR%"
"%RPG_STT_PYTHON%" -c "import os; os.environ['NEMO_CACHE_DIR'] = r'%OMNIX_STT_MODELS_DIR%'; from nemo.collections.asr.models import ASRModel; ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); print('Parakeet model downloaded successfully!')" 2>nul
if errorlevel 1 (
    echo WARNING: Failed to pre-download Parakeet model
    echo It will be downloaded on first use instead
)

echo.
echo [VERIFY][STT] Verifying STT runtime...
"%RPG_STT_PYTHON%" -c "import torch, torchvision, torchaudio; print('torch:', torch.__version__); print('torchvision:', torchvision.__version__); print('torchaudio:', torchaudio.__version__)"
"%RPG_STT_PYTHON%" -c "import nemo.collections.asr as nemo_asr; print('NeMo ASR: OK')"
if errorlevel 1 (
    echo ERROR: Verification failed for %RPG_STT_ENV%
    pause
    exit /b 1
)

echo.
echo =============================================
echo Setup Complete!
echo =============================================
echo.
echo Environments:
echo   - %RPG_FLUX_ENV% : main app + FLUX
echo   - %RPG_TTS_ENV%  : vendored Qwen3-TTS
echo   - %RPG_STT_ENV%  : Parakeet STT only
echo.
echo Python interpreters:
echo   - %RPG_FLUX_PYTHON%
echo   - %RPG_TTS_PYTHON%
echo   - %RPG_STT_PYTHON%
echo.
echo IMPORTANT:
echo   - Do not rely on bare python or pip
echo   - Do not rely on project venv for FLUX/TTS/STT services
echo   - start_all.bat must use exact interpreter paths
echo.
pause
endlocal

:error
echo.
echo =============================================
echo SETUP FAILED
echo =============================================
pause
exit /b 1
