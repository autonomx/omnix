@echo off
setlocal

REM ============================================================
REM Omnix - Standalone Qwen3-TTS model downloader
REM Downloads only the Qwen3-TTS model into resources\models\tts
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "OMNIX_REPO_ROOT=%SCRIPT_DIR%"
if "%OMNIX_REPO_ROOT:~-1%"=="\" set "OMNIX_REPO_ROOT=%OMNIX_REPO_ROOT:~0,-1%"

set "CONDA_ROOT=%USERPROFILE%\miniconda3"
set "RPG_TTS_ENV=rpg-tts"
set "RPG_TTS_PYTHON=%CONDA_ROOT%\envs\%RPG_TTS_ENV%\python.exe"

set "OMNIX_MODELS_ROOT=%OMNIX_REPO_ROOT%\resources\models"
set "OMNIX_TTS_MODELS_DIR=%OMNIX_MODELS_ROOT%\tts"
set "OMNIX_QWEN3_TTS_MODEL_DIR=%OMNIX_TTS_MODELS_DIR%\Qwen3-TTS-12Hz-0.6B-Base"
set "OMNIX_QWEN3_TTS_REPO_ID=Qwen/Qwen3-TTS-12Hz-0.6B-Base"

echo =============================================
echo Omnix - Download Qwen3-TTS only
echo =============================================
echo Repo root: %OMNIX_REPO_ROOT%
echo TTS python: %RPG_TTS_PYTHON%
echo Model repo: %OMNIX_QWEN3_TTS_REPO_ID%
echo Target dir: %OMNIX_QWEN3_TTS_MODEL_DIR%
echo.

if not exist "%RPG_TTS_PYTHON%" (
    echo ERROR: rpg-tts python not found:
    echo   %RPG_TTS_PYTHON%
    echo.
    echo Make sure the rpg-tts conda environment exists first.
    pause
    exit /b 1
)

if not exist "%OMNIX_MODELS_ROOT%" mkdir "%OMNIX_MODELS_ROOT%"
if not exist "%OMNIX_TTS_MODELS_DIR%" mkdir "%OMNIX_TTS_MODELS_DIR%"

echo [1/4] Checking huggingface_hub in rpg-tts...
"%RPG_TTS_PYTHON%" -c "import huggingface_hub; print('huggingface_hub', huggingface_hub.__version__)"
if errorlevel 1 (
    echo ERROR: huggingface_hub is not available in %RPG_TTS_ENV%
    pause
    exit /b 1
)

echo.
echo [2/4] Removing existing target directory for clean test...
if exist "%OMNIX_QWEN3_TTS_MODEL_DIR%" (
    rmdir /s /q "%OMNIX_QWEN3_TTS_MODEL_DIR%"
)
mkdir "%OMNIX_QWEN3_TTS_MODEL_DIR%"
if errorlevel 1 (
    echo ERROR: Could not create target directory:
    echo   %OMNIX_QWEN3_TTS_MODEL_DIR%
    pause
    exit /b 1
)

echo.
echo [3/4] Downloading and copying Qwen3-TTS snapshot...
"%RPG_TTS_PYTHON%" -c "from huggingface_hub import snapshot_download; import pathlib, shutil; repo_id=r'%OMNIX_QWEN3_TTS_REPO_ID%'; target=pathlib.Path(r'%OMNIX_QWEN3_TTS_MODEL_DIR%'); snapshot=pathlib.Path(snapshot_download(repo_id=repo_id)); print('HF snapshot:', snapshot); [shutil.copy2(p, target / p.name) if p.is_file() else shutil.copytree(p, target / p.name, dirs_exist_ok=True) for p in snapshot.iterdir()]; print('Final target:', target); print('Final target contents:', sorted([p.name for p in target.iterdir()]))"
if errorlevel 1 (
    echo ERROR: Qwen3-TTS download/copy failed
    echo.
    echo Target directory contents after failure:
    dir "%OMNIX_QWEN3_TTS_MODEL_DIR%" 2>nul
    pause
    exit /b 1
)

echo.
echo [4/4] Verifying required files...
if not exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\config.json" (
    echo ERROR: Missing config.json
    dir "%OMNIX_QWEN3_TTS_MODEL_DIR%" 2>nul
    pause
    exit /b 1
)

if not exist "%OMNIX_QWEN3_TTS_MODEL_DIR%\preprocessor_config.json" (
    echo ERROR: Missing preprocessor_config.json
    dir "%OMNIX_QWEN3_TTS_MODEL_DIR%" 2>nul
    pause
    exit /b 1
)

dir /b "%OMNIX_QWEN3_TTS_MODEL_DIR%\*.safetensors" >nul 2>nul
if errorlevel 1 (
    echo ERROR: No .safetensors files found
    dir "%OMNIX_QWEN3_TTS_MODEL_DIR%" 2>nul
    pause
    exit /b 1
)

echo.
echo SUCCESS: Qwen3-TTS model downloaded successfully
echo Model dir:
echo   %OMNIX_QWEN3_TTS_MODEL_DIR%
echo.
dir "%OMNIX_QWEN3_TTS_MODEL_DIR%"
echo.
pause
exit /b 0
