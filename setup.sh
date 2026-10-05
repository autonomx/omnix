#!/bin/bash

# ============================================
# Omnix - Split Runtime Setup Script (Linux/Mac)
# ============================================

OMNIX_REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$OMNIX_REPO_ROOT"

# Default conda root - adjust this path for your system
CONDA_ROOT="${CONDA_ROOT:-$HOME/miniconda3}"
CONDA_EXE="$CONDA_ROOT/bin/conda"

RPG_FLUX_ENV="rpg-flux"
RPG_FLUX_PYTHON="$CONDA_ROOT/envs/$RPG_FLUX_ENV/bin/python"

RPG_TTS_ENV="rpg-tts"
RPG_TTS_PYTHON="$CONDA_ROOT/envs/$RPG_TTS_ENV/bin/python"

RPG_STT_ENV="rpg-stt"
RPG_STT_PYTHON="$CONDA_ROOT/envs/$RPG_STT_ENV/bin/python"

OMNIX_MODELS_ROOT="$OMNIX_REPO_ROOT/resources/models"
OMNIX_LLM_MODELS_DIR="$OMNIX_MODELS_ROOT/llm"
OMNIX_TTS_MODELS_DIR="$OMNIX_MODELS_ROOT/tts"
OMNIX_STT_MODELS_DIR="$OMNIX_MODELS_ROOT/stt"
OMNIX_IMAGE_MODELS_DIR="$OMNIX_MODELS_ROOT/image"

OMNIX_QWEN3_TTS_MODEL_DIR="$OMNIX_TTS_MODELS_DIR/Qwen3-TTS-12Hz-0.6B-Base"
OMNIX_QWEN3_TTS_REPO_ID="Qwen/Qwen3-TTS-12Hz-0.6B-Base"

echo "============================================="
echo "Omnix - Setup with Split Conda Environments"
echo "============================================="
echo ""
echo "This will install all dependencies for:"
echo "  - Main app + FLUX image generation in $RPG_FLUX_ENV"
echo "  - Vendored Qwen3-TTS in $RPG_TTS_ENV"
echo "  - Parakeet STT in $RPG_STT_ENV"
echo "  - Hermes Agent sidecar setup"
echo ""
echo "Setup will start automatically in 3 seconds..."
sleep 3

error() {
    echo ""
    echo "============================================="
    echo "SETUP FAILED"
    echo "============================================="
    read -p "Press Enter to exit..."
    exit 1
}

if [ ! -f "$CONDA_EXE" ]; then
    echo "ERROR: conda not found:"
    echo "  $CONDA_EXE"
    echo "Please install Miniconda3 first or adjust CONDA_ROOT path"
    error
fi

if [ ! -f "$RPG_FLUX_PYTHON" ]; then
    echo "Creating conda environment: $RPG_FLUX_ENV"
    "$CONDA_EXE" create -n $RPG_FLUX_ENV python=3.11 -y
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create $RPG_FLUX_ENV"
        error
    fi
fi

if [ ! -f "$RPG_TTS_PYTHON" ]; then
    echo "Creating conda environment: $RPG_TTS_ENV"
    "$CONDA_EXE" create -n $RPG_TTS_ENV python=3.11 -y
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create $RPG_TTS_ENV"
        error
    fi
fi

if [ ! -f "$RPG_STT_PYTHON" ]; then
    echo "Creating conda environment: $RPG_STT_ENV"
    "$CONDA_EXE" create -n $RPG_STT_ENV python=3.11 -y
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create $RPG_STT_ENV"
        error
    fi
fi

if [ ! -f "src/services/image/image.linux.lock.txt" ]; then
    echo "ERROR: Hashed image runtime lock not found"
    echo "Expected: src/services/image/image.linux.lock.txt"
    error
fi

if [ ! -f "src/services/tts/tts.linux.lock.txt" ]; then
    echo "ERROR: Hashed TTS runtime lock not found"
    echo "Expected: src/services/tts/tts.linux.lock.txt"
    error
fi

if [ ! -f "src/services/stt/stt.linux.lock.txt" ]; then
    echo "ERROR: Hashed STT runtime lock not found"
    echo "Expected: src/services/stt/stt.linux.lock.txt"
    error
fi

echo ""
echo "[ENV CHECK] FLUX"
"$RPG_FLUX_PYTHON" -c "import sys; print('FLUX Python:', sys.executable); assert sys.version_info[:2] == (3, 11), sys.version"
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to verify $RPG_FLUX_ENV"
    error
fi

echo ""
echo "[ENV CHECK] STT"
"$RPG_STT_PYTHON" -c "import sys; print('STT Python:', sys.executable); assert sys.version_info[:2] == (3, 11), sys.version"
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to verify $RPG_STT_ENV"
    error
fi

echo ""
echo "[ENV CHECK] TTS"
"$RPG_TTS_PYTHON" -c "import sys; print('TTS Python:', sys.executable); assert sys.version_info[:2] == (3, 11), sys.version"
if [ $? -ne 0 ]; then
    echo "ERROR: $RPG_TTS_ENV must use Python 3.11"
    error
fi

echo ""
echo "============================================="
echo "Installing main app + FLUX into $RPG_FLUX_ENV"
echo "============================================="

if [ ! -f "src/app/providers/vendor/faster_qwen3_tts/__init__.py" ]; then
    echo "ERROR: Vendored faster_qwen3_tts package not found"
    echo "Expected:"
    echo "  src/app/providers/vendor/faster_qwen3_tts/__init__.py"
    error
fi

if [ ! -f "src/app/providers/vendor/qwen_tts/__init__.py" ]; then
    echo "ERROR: Vendored qwen_tts package not found"
    echo "Expected:"
    echo "  src/app/providers/vendor/qwen_tts/__init__.py"
    error
fi

echo "[1/10][FLUX] Checking pip..."
"$RPG_FLUX_PYTHON" -m pip --version

echo ""
echo "[2/10][FLUX] Removing conflicting torch packages..."
"$RPG_FLUX_PYTHON" -m pip uninstall -y torch torchvision torchaudio
"$RPG_FLUX_PYTHON" -m pip uninstall -y torchtext torchdata

echo ""
echo "[3/10][FLUX] Installing the hashed image runtime lock..."
"$RPG_FLUX_PYTHON" -m pip install --no-cache-dir --force-reinstall --require-hashes -r src/services/image/image.linux.lock.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install the locked image runtime into $RPG_FLUX_ENV"
    error
fi

echo ""
echo "[FLUX] Cleaning conflicting pip-installed TTS packages..."

# These packages conflict with the vendored Qwen3-TTS runtime and can
# force incompatible transformers/accelerate versions into the env.
# We explicitly remove them to guarantee a clean deterministic runtime.

"$RPG_FLUX_PYTHON" -m pip uninstall -y faster-qwen3-tts >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  removed faster-qwen3-tts"
else
    echo "  faster-qwen3-tts not present"
fi

"$RPG_FLUX_PYTHON" -m pip uninstall -y qwen-tts >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  removed qwen-tts"
else
    echo "  qwen-tts not present"
fi

# Optional: clear HF cache metadata for these packages (safe no-op if not present)
# Uncomment if you see persistent version bleed-through issues
# rm -rf "$HOME/.cache/huggingface/modules/transformers_modules" 2>/dev/null

echo "[FLUX] Cleanup complete."

echo ""
echo "[4/10][FLUX] Gateway requirements are included in src/services/image/image.linux.lock.txt."

echo ""
echo "[5/10][FLUX] FLUX requirements are included in src/services/image/image.linux.lock.txt."

echo ""
echo "[6/10][FLUX] TTS moved to dedicated $RPG_TTS_ENV environment"

echo ""
echo "[7/10][FLUX] Runtime dependency pins are managed by src/services/image/image.in and its hashed lock."

echo ""
echo "[8/10][FLUX] Downloading default LLM (Qwen3-4B Q8_0)..."
mkdir -p "$OMNIX_LLM_MODELS_DIR"
"$RPG_FLUX_PYTHON" -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='qwen/Qwen3-4B-Instruct-2507-GGUF', filename='qwen3-4b-instruct-2507-q8_0.gguf', local_dir='$OMNIX_LLM_MODELS_DIR', local_dir_use_symlinks=False)" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "WARNING: Could not auto-download Qwen3-4B GGUF model"
else
    echo "Qwen3-4B model downloaded to $OMNIX_LLM_MODELS_DIR/"
fi

echo ""
echo "[9/10][FLUX] Downloading the Memory v2 embedding model (multilingual-e5-small)..."
if ! PYTHONPATH="$OMNIX_REPO_ROOT/src" "$RPG_FLUX_PYTHON" -m app.assistant_memory.v2.embeddings download; then
    echo "WARNING: Could not download the Memory v2 embedding model. Memory retrieval will match words only."
    echo "         Retry later with: PYTHONPATH=src \"$RPG_FLUX_PYTHON\" -m app.assistant_memory.v2.embeddings download"
fi

echo ""
echo "[10/10][FLUX] Verifying main app runtime..."
export PYTHONPATH="$OMNIX_REPO_ROOT/src"
"$RPG_FLUX_PYTHON" -c "import torch, torchvision, torchaudio; print('torch:', torch.__version__); print('torchvision:', torchvision.__version__); print('torchaudio:', torchaudio.__version__)"
"$RPG_FLUX_PYTHON" -c "import torch; print('torch:', torch.__version__)"
if [ $? -ne 0 ]; then
    error
fi
"$RPG_FLUX_PYTHON" -c "import torchvision; print('torchvision:', torchvision.__version__)"
if [ $? -ne 0 ]; then
    error
fi
"$RPG_FLUX_PYTHON" -c "import diffusers; print('diffusers OK')"
if [ $? -ne 0 ]; then
    error
fi
"$RPG_FLUX_PYTHON" -c "from app.rpg.visual.runtime_status import validate_flux_klein_runtime; s=validate_flux_klein_runtime(); print('FLUX:', 'READY' if s.get('ready') else 'NOT READY', s.get('error','')); raise SystemExit(0 if s.get('ready') else 1)"
if [ $? -ne 0 ]; then
    error
fi
echo "[FLUX] Runtime verification complete."
echo "============================================="
echo "FLUX: READY"
echo "============================================="

echo ""
echo "============================================="
echo "Installing dedicated TTS service into $RPG_TTS_ENV"
echo "============================================="

echo ""
echo "[1/7][TTS] Checking pip..."
"$RPG_TTS_PYTHON" -m pip --version
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[2/7][TTS] Removing conflicting torch packages..."
"$RPG_TTS_PYTHON" -m pip uninstall -y torch torchvision torchaudio
"$RPG_TTS_PYTHON" -m pip uninstall -y torchtext torchdata

echo ""
echo "[3/7][TTS] Installing the hashed TTS runtime lock..."
"$RPG_TTS_PYTHON" -m pip install --no-cache-dir --force-reinstall --require-hashes -r src/services/tts/tts.linux.lock.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install the locked TTS runtime into $RPG_TTS_ENV"
    error
fi

echo ""
echo "[4/7][TTS] Verifying torch CUDA build..."
"$RPG_TTS_PYTHON" -c "import torch, torchaudio; print('torch:', torch.__version__); print('torchaudio:', torchaudio.__version__); print('torch_cuda:', torch.version.cuda); print('cuda_available:', torch.cuda.is_available())"
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[5/7][TTS] TTS requirements and torch pins are included in src/services/tts/tts.linux.lock.txt."

echo ""
echo "============================================="
echo "Downloading Qwen3-TTS model"
echo "============================================="

if [ -f "$OMNIX_REPO_ROOT/download_tts_only.sh" ]; then
    chmod +x "$OMNIX_REPO_ROOT/download_tts_only.sh"
    "$OMNIX_REPO_ROOT/download_tts_only.sh"
    if [ $? -ne 0 ]; then
        error
    fi
fi

echo ""
echo "[6/7][TTS] Checking local Qwen3-TTS files..."
"$RPG_TTS_PYTHON" -c "from pathlib import Path; p=Path('$OMNIX_QWEN3_TTS_MODEL_DIR'); shards=list(p.glob('*.safetensors')); print('model_dir:', p); print('safetensors_shards:', [s.name for s in shards]); assert (p/'config.json').exists(), 'Missing config.json'; assert (p/'preprocessor_config.json').exists(), 'Missing preprocessor_config.json'; assert shards, 'No safetensors shards found'"
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[7/7][TTS] Attempting real local from_pretrained load..."
"$RPG_TTS_PYTHON" -c "import sys; sys.path.insert(0, '$OMNIX_REPO_ROOT/src'); from app.providers.vendor.qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel; model_dir='$OMNIX_QWEN3_TTS_MODEL_DIR'; print('Loading from:', model_dir); model = Qwen3TTSModel.from_pretrained(model_dir); print('Qwen3TTSModel local load OK:', type(model).__name__)"
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[VERIFY][TTS] transformers/tokenizers/onnxruntime versions."
"$RPG_TTS_PYTHON" -c "import transformers, tokenizers, onnxruntime; print('transformers:', transformers.__version__); print('tokenizers:', tokenizers.__version__); print('onnxruntime:', onnxruntime.__version__)"
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[POST-CHECK][TTS] Verifying tts_server import..."
"$RPG_TTS_PYTHON" -c "import sys; sys.path.insert(0, '$OMNIX_REPO_ROOT/src'); from services.tts import tts_server; print('tts_server import OK')"
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[POST-CHECK][TTS] Verifying HTTP TTS contract boot path..."
"$RPG_TTS_PYTHON" -c "import sys; sys.path.insert(0, '$OMNIX_REPO_ROOT/src'); from services.tts import tts_server; app = tts_server.app; print('tts_server app OK')"
if [ $? -ne 0 ]; then
    error
fi

echo ""
echo "[POST-CHECK][TTS] Verifying provider status helper..."
"$RPG_TTS_PYTHON" -c "import sys; sys.path.insert(0, '$OMNIX_REPO_ROOT/src'); from services.tts import tts_server; s = tts_server.get_tts_service_status(); print('TTS:', 'READY' if s.get('ok') else 'NOT READY', s.get('error',''))"
if [ $? -ne 0 ]; then
    error
fi

echo "[TTS] Runtime verification complete."

echo ""
echo "============================================="
echo "Installing Parakeet STT into $RPG_STT_ENV"
echo "============================================="

echo "[1/7][STT] Checking pip..."
"$RPG_STT_PYTHON" -m pip --version
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to upgrade pip tools in $RPG_STT_ENV"
    error
fi

echo ""
echo "[2/7][STT] Removing conflicting torch packages..."
"$RPG_STT_PYTHON" -m pip uninstall -y torch torchvision torchaudio

echo ""
echo "[3/7][STT] Installing the hashed STT runtime lock..."
"$RPG_STT_PYTHON" -m pip install --no-cache-dir --force-reinstall --require-hashes -r src/services/stt/stt.linux.lock.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install the locked STT runtime into $RPG_STT_ENV"
    error
fi

echo ""
echo "[5/7][STT] Torch and Transformers pins are included in src/services/stt/stt.linux.lock.txt."

echo ""
echo "[7/7][STT] Pre-downloading Parakeet model..."
mkdir -p "$OMNIX_STT_MODELS_DIR"
"$RPG_STT_PYTHON" -c "import os; os.environ['NEMO_CACHE_DIR'] = '$OMNIX_STT_MODELS_DIR'; from nemo.collections.asr.models import ASRModel; ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); print('Parakeet model downloaded successfully!')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to pre-download Parakeet model"
    echo "It will be downloaded on first use instead"
fi

echo ""
echo "[VERIFY][STT] Verifying STT runtime..."
"$RPG_STT_PYTHON" -c "import torch, torchvision, torchaudio; print('torch:', torch.__version__); print('torchvision:', torchvision.__version__); print('torchaudio:', torchaudio.__version__)"
"$RPG_STT_PYTHON" -c "import nemo.collections.asr as nemo_asr; print('NeMo ASR: OK')"
if [ $? -ne 0 ]; then
    echo "ERROR: Verification failed for $RPG_STT_ENV"
    error
fi

echo ""
echo "============================================="
echo "Installing Hermes Agent sidecar"
echo "============================================="
if [ "${OMNIX_SKIP_HERMES_SETUP:-0}" = "1" ]; then
    echo "Skipping Hermes setup because OMNIX_SKIP_HERMES_SETUP=1."
elif [ -f "$OMNIX_REPO_ROOT/scripts/setup_hermes.sh" ]; then
    chmod +x "$OMNIX_REPO_ROOT/scripts/setup_hermes.sh"
    "$OMNIX_REPO_ROOT/scripts/setup_hermes.sh"
    if [ $? -ne 0 ]; then
        echo "ERROR: Hermes Agent sidecar setup failed"
        error
    fi
else
    echo "ERROR: scripts/setup_hermes.sh not found"
    error
fi

echo ""
echo "============================================="
echo "Installing governed browser and MCP tools"
echo "============================================="
chmod +x "$OMNIX_REPO_ROOT/scripts/setup_agent_tools.sh"
"$OMNIX_REPO_ROOT/scripts/setup_agent_tools.sh"
if [ $? -ne 0 ]; then
    echo "ERROR: Governed browser/MCP tool setup failed"
    error
fi

echo ""
echo "[PostgreSQL] Local database (docker-compose.postgres.yml)"
OMNIX_POSTGRES_PORT="${OMNIX_POSTGRES_PORT:-5432}"
if "$RPG_FLUX_PYTHON" -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1', int('$OMNIX_POSTGRES_PORT'))) == 0 else 1)"; then
    echo "PostgreSQL is already listening on 127.0.0.1:$OMNIX_POSTGRES_PORT; leaving it as it is."
elif command -v docker >/dev/null 2>&1; then
    # Only a machine without a database gets one; an existing install is never touched.
    if docker compose -f "$OMNIX_REPO_ROOT/docker-compose.postgres.yml" up -d --wait; then
        echo "PostgreSQL started. Set OMNIX_DATABASE_URL and run: PYTHONPATH=src \"$RPG_FLUX_PYTHON\" -m app.persistence migrate"
    else
        echo "WARNING: Could not start PostgreSQL with Docker; see docs/SETUP.md (PostgreSQL)."
    fi
else
    echo "WARNING: Docker not found and nothing listens on $OMNIX_POSTGRES_PORT; install PostgreSQL 17 (docs/SETUP.md)."
fi

echo ""
echo "============================================="
echo "Setup Complete!"
echo "============================================="
echo ""
echo "Environments:"
echo "  - $RPG_FLUX_ENV : main app + FLUX"
echo "  - $RPG_TTS_ENV  : vendored Qwen3-TTS"
echo "  - $RPG_STT_ENV  : Parakeet STT only"
echo "  - Hermes Agent sidecar : installed/configured via scripts/setup_hermes.sh"
echo "  - agent-browser + MCPorter : installed/configured via scripts/setup_agent_tools.sh"
echo ""
echo "Python interpreters:"
echo "  - $RPG_FLUX_PYTHON"
echo "  - $RPG_TTS_PYTHON"
echo "  - $RPG_STT_PYTHON"
echo ""
echo "IMPORTANT:"
echo "  - Do not rely on bare python or pip"
echo "  - Do not rely on project venv for FLUX/TTS/STT services"
echo "  - start_all.sh must use exact interpreter paths"
echo ""
read -p "Press Enter to exit..."
