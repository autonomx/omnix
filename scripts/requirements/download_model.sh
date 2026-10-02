#!/bin/bash
# Download Qwen2.5-4B GGUF model for llama.cpp
# This script downloads the quantized GGUF model from HuggingFace

echo "============================================"
echo "Downloading Mistral-7B GGUF Model"
echo "============================================"
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OMNIX_REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
cd "$OMNIX_REPO_ROOT"

# Create the shared models directory if it doesn't exist
mkdir -p resources/models/llm

CONDA_ROOT="${CONDA_ROOT:-$HOME/miniconda3}"
RPG_FLUX_PYTHON="${RPG_FLUX_PYTHON:-$CONDA_ROOT/envs/rpg-flux/bin/python}"
if [ ! -x "$RPG_FLUX_PYTHON" ]; then
    echo "ERROR: The locked image runtime was not found. Run ./setup.sh first."
    exit 1
fi
"$RPG_FLUX_PYTHON" -c 'import sys, huggingface_hub; assert sys.version_info[:2] == (3, 11)'
if [ $? -ne 0 ]; then
    echo "ERROR: Activate the Python 3.11 rpg-flux runtime installed by setup.sh."
    exit 1
fi

# Download Mistral-7B GGUF model (TheBloke)
# Using Q4_K_M quantization - good balance of size and quality
echo "Downloading mistral-7b-instruct-v0.2.Q4_K_M.gguf..."
echo "This may take a few minutes depending on your internet speed..."
echo ""

"$RPG_FLUX_PYTHON" -c "
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

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================"
    echo "Download complete!"
    echo "Model saved to: resources/models/llm/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    echo "============================================"
else
    echo ""
    echo "============================================"
    echo "Download failed. Please try again."
    echo "============================================"
    exit 1
fi
