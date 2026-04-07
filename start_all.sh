#!/bin/bash

echo "================================================"
echo "Omnix - Full Launcher"
echo "================================================"
echo ""
echo "This will start:"
echo "  1. Parakeet STT Server (port 8000) - Voice recognition"
echo "  2. Omnix FastAPI Server (port 5000) - Main application + WebSocket TTS"
echo ""
echo "Note: Make sure LM Studio is running with a model loaded."
echo "      Or use Cerebras/OpenRouter API in settings."
echo ""
echo "Starting services..."
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Cleanup existing server processes
echo "[Cleanup] Killing existing server processes on ports 5000 and 8000..."
kill $(lsof -ti:5000) 2>/dev/null
kill $(lsof -ti:8000) 2>/dev/null
sleep 2
echo "[Cleanup] Done."

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    echo "[Setup] Activating virtual environment..."
    source venv/bin/activate
else
    echo "WARNING: Virtual environment not found. Creating now..."
    python3 -m venv venv
    source venv/bin/activate
    echo "[Setup] Installing faster-qwen3-tts in virtual environment..."
    pip install faster-qwen3-tts>=0.2.4
    echo "[Setup] Virtual environment created and faster-qwen3-tts installed."
fi

# Check if PyTorch is already installed
echo "[Setup] Checking PyTorch installation..."
python -c "import torch; print('PyTorch already installed:', torch.__version__)" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[Setup] PyTorch not found, installing CUDA-enabled PyTorch for RTX 4090 compatibility..."
    pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 --index-url https://download.pytorch.org/whl/cu124
else
    echo "[Setup] PyTorch already installed, skipping download."
fi

# Check if faster-qwen3-tts is already installed
echo "[Setup] Checking faster-qwen3-tts installation..."
python -c "import faster_qwen3_tts; print('faster-qwen3-tts already installed:', faster_qwen3_tts.__version__)" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[Setup] faster-qwen3-tts not found, installing..."
    pip install faster-qwen3-tts>=0.2.4
else
    echo "[Setup] faster-qwen3-tts already installed, skipping download."
fi

# Install other dependencies
echo "[Setup] Installing Python dependencies..."
pip install -q fastapi uvicorn websockets aiohttp pydub numpy soundfile 2>/dev/null

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $STT_PID $CHATBOT_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start Parakeet STT Server in background
echo "[1/2] Starting Parakeet STT Server on port 8000..."
if [ -f "$SCRIPT_DIR/parakeet_stt_server.py" ]; then
    python parakeet_stt_server.py &
    STT_PID=$!
else
    echo "WARNING: parakeet_stt_server.py not found - STT will not be available"
    echo "Run setup to install nemo_toolkit[asr]."
    STT_PID=""
fi

# Wait a bit for STT to start
sleep 5


# Start Omnix FastAPI Server (supports WebSocket TTS streaming)
echo "[2/2] Starting Omnix FastAPI Server on port 5000..."
echo ""
python app.py &
CHATBOT_PID=$!

# Wait for chatbot
wait $CHATBOT_PID

# Cleanup when done
cleanup