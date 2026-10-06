@echo off
REM Download Qwen2.5-4B GGUF model for llama.cpp
REM This script downloads the quantized GGUF model from HuggingFace

echo ============================================
echo Downloading Qwen2.5-4B GGUF Model
echo ============================================
echo.

set "OMNIX_REPO_ROOT=%~dp0..\.."
for %%I in ("%OMNIX_REPO_ROOT%") do set "OMNIX_REPO_ROOT=%%~fI"
cd /d "%OMNIX_REPO_ROOT%"

REM Create the shared models directory if it doesn't exist
if not exist "resources\models\llm" mkdir resources\models\llm

if not defined CONDA_ROOT set "CONDA_ROOT=%USERPROFILE%\miniconda3"
if not defined RPG_FLUX_PYTHON set "RPG_FLUX_PYTHON=%CONDA_ROOT%\envs\rpg-flux\python.exe"
if not exist "%RPG_FLUX_PYTHON%" (
    echo ERROR: The locked image runtime was not found. Run setup.bat first.
    exit /b 1
)
"%RPG_FLUX_PYTHON%" -c "import sys, huggingface_hub; assert sys.version_info[:2] == (3, 11)"
if errorlevel 1 (
    echo ERROR: Activate the Python 3.11 rpg-flux runtime installed by setup.bat.
    exit /b 1
)

REM Download Mistral-7B GGUF model (TheBloke)
REM Using Q4_K_M quantization - good balance of size and quality
echo Downloading Mistral-7B-Instruct-v0.2-Q4_K_M.gguf...
echo This may take a few minutes depending on your internet speed...
echo.

"%RPG_FLUX_PYTHON%" -c "
from huggingface_hub import hf_hub_download
import os

# Download the Q4_K_M quantized model
filename = hf_hub_download(
    repo_id='TheBloke/Mistral-7B-Instruct-v0.2-GGUF',
    filename='mistral-7b-instruct-v0.2.Q4_K_M.gguf',
    local_dir='resources/models/llm'
)
print(f'Downloaded to: {filename}')
"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo Download complete!
    echo Model saved to: resources\models\llm\mistral-7b-instruct-v0.2.Q4_K_M.gguf
    echo ============================================
) else (
    echo.
    echo ============================================
    echo Download failed. Please try again.
    echo ============================================
    exit /b 1
)
