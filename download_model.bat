@echo off
REM Download Qwen2.5-4B GGUF model for llama.cpp
REM This script downloads the quantized GGUF model from HuggingFace

echo ============================================
echo Downloading Qwen2.5-4B GGUF Model
echo ============================================
echo.

REM Create the shared models directory if it doesn't exist
if not exist "resources\models\llm" mkdir resources\models\llm

REM Install huggingface-cli if not available
pip install huggingface-hub --quiet

REM Download Mistral-7B GGUF model (TheBloke)
REM Using Q4_K_M quantization - good balance of size and quality
echo Downloading Mistral-7B-Instruct-v0.2-Q4_K_M.gguf...
echo This may take a few minutes depending on your internet speed...
echo.

python -c "
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
