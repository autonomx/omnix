#!/bin/bash

# ============================================
# Omnix - Setup Script (Linux/Mac)
# ============================================

echo "============================================="
echo "Omnix - Setup with Virtual Environment"
echo "============================================="
echo ""
echo "This will install all dependencies for:"
echo "  - Chatbot Web Server"
echo "  - Parakeet STT (Speech-to-Text)"
echo "  - FasterQwen3TTS (Text-to-Speech)"
echo ""
echo "Using Python virtual environment for isolation"
read -p "Press Enter to continue..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "ERROR: Python is not installed or not in PATH"
        echo "Please install Python 3.10 or higher from https://www.python.org/"
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# Check Python version
echo "Using Python: $($PYTHON_CMD --version)"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo ""
echo "[1/7] Creating Python virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists, removing..."
    rm -rf venv
fi

$PYTHON_CMD -m venv venv
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate
echo "Virtual environment activated"

echo ""
echo "[2/7] Upgrading pip..."
pip install --upgrade pip

echo ""
echo "[3/7] Installing PyTorch with CUDA 12.4 support..."
echo "This is CRITICAL - mismatched versions cause errors"
echo ""
pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 --index-url https://download.pytorch.org/whl/cu124
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to install PyTorch with CUDA"
    echo "Trying CPU-only version..."
    pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
fi

echo ""
echo "[4/7] Installing torchmetrics..."
pip install torchmetrics==1.4.2

echo ""
echo "[5/7] Installing core dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install core dependencies"
    exit 1
fi

echo ""
echo "[6/8] Installing FasterQwen3TTS..."
pip install faster-qwen3-tts>=0.2.4
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to install FasterQwen3TTS"
    echo "You can try: pip install faster-qwen3-tts"
fi

echo ""
echo "[7/8] Installing NeMo ASR for Parakeet STT..."
pip install "nemo_toolkit[asr]"
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to install NeMo ASR"
    echo "STT will not be available"
    echo "Try: pip install nemo_toolkit[asr]"
fi

echo ""
echo "[8/8] Installing compatible transformers version..."
echo "Note: nemo_toolkit installs transformers 4.53+ which may break compatibility"
echo "Installing transformers==4.46.3 for better compatibility..."
pip install transformers==4.46.3 tokenizers==0.20.3 --force-reinstall

echo ""
echo "[9/9] Pre-downloading Parakeet TDT 0.6B model..."
echo "This may take a few minutes..."
echo "Note: Model downloads to HuggingFace cache: ~/.cache/huggingface/"
python -c "from nemo.collections.asr.models import ASRModel; ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); print('Parakeet model downloaded successfully!')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to pre-download Parakeet model"
    echo "It will be downloaded on first use instead"
fi

echo ""
echo "[10/10] Downloading default LLM (Qwen3-4B Q8_0)..."
echo "This provides an immediate working LLM for new installations"
echo "Model: qwen/Qwen3-4B-Instruct-2507-GGUF"
echo "Quantization: Q8_0 (~4GB)"
echo ""

# Create models directory
mkdir -p models/llm

# Download using huggingface_hub
echo "Downloading Qwen3-4B GGUF model..."
python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='qwen/Qwen3-4B-Instruct-2507-GGUF', filename='qwen3-4b-instruct-2507-q8_0.gguf', local_dir='models/llm', local_dir_use_symlinks=False)" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Could not auto-download - will provide manual instructions below"
else
    echo "Qwen3-4B model downloaded to models/llm/"
fi

echo ""
echo "[11/11] Verifying installations..."
echo ""

# Check PyTorch
python -c "import torch; print(f'PyTorch: {torch.__version__}')" 2>/dev/null
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')" 2>/dev/null

# Check TTS
python -c "import faster_qwen3_tts; print('FasterQwen3TTS: OK')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "FasterQwen3TTS: FAILED - check faster-qwen3-tts installation"
fi

# Check STT
python -c "import nemo.collections.asr as nemo_asr; print('NeMo ASR: OK')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "NeMo ASR: FAILED - check nemo_toolkit installation"
fi

echo ""
echo "============================================="
echo "Setup Complete!"
echo "============================================="
echo ""
echo "IMPORTANT NOTES:"
echo "  - Virtual environment created in 'venv' directory"
echo "  - To activate: source venv/bin/activate (Linux/Mac) or venv\Scripts\activate (Windows)"
echo "  - To deactivate: deactivate"
echo "  - PyTorch must match torchvision version"
echo "  - Use parakeet_stt_server.py from root (not models folder)"
echo "  - transformers will be updated to 4.53.x by nemo_toolkit"
echo ""
echo "To start services:"
echo "  ./start_all.sh             - Start all services"
echo "  ./start_parakeet_stt.sh    - Start STT only"
echo ""
echo "To run with virtual environment:"
echo "  source venv/bin/activate && ./start_all.sh"
echo ""
