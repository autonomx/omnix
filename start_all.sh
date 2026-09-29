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

CONDA_ROOT="${CONDA_ROOT:-$HOME/miniconda3}"
RPG_FLUX_ENV="${RPG_FLUX_ENV:-rpg-flux}"
RPG_STT_ENV="${RPG_STT_ENV:-rpg-stt}"
RPG_FLUX_PYTHON="${RPG_FLUX_PYTHON:-$CONDA_ROOT/envs/$RPG_FLUX_ENV/bin/python}"
RPG_STT_PYTHON="${RPG_STT_PYTHON:-$CONDA_ROOT/envs/$RPG_STT_ENV/bin/python}"

if [ ! -x "$RPG_FLUX_PYTHON" ] || [ ! -x "$RPG_STT_PYTHON" ]; then
    echo "ERROR: Locked FLUX or STT runtime is missing. Run ./setup.sh first."
    exit 1
fi
for runtime_python in "$RPG_FLUX_PYTHON" "$RPG_STT_PYTHON"; do
    "$runtime_python" -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version'
    if [ $? -ne 0 ]; then
        echo "ERROR: Omnix runtimes require Python 3.11: $runtime_python"
        exit 1
    fi
done
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

# Every child entrypoint validates public binding against OMNIX_ALLOW_LAN.
export OMNIX_BIND_HOST="${OMNIX_BIND_HOST:-127.0.0.1}"

if [ -x "$SCRIPT_DIR/.tools/npm-global/bin/agent-browser" ]; then
    export PATH="$SCRIPT_DIR/.tools/npm-global/bin:$PATH"
    export OMNIX_AGENT_BROWSER_COMMAND="$SCRIPT_DIR/.tools/npm-global/bin/agent-browser"
fi
if [ -x "$SCRIPT_DIR/.tools/npm-global/bin/mcporter" ]; then
    export PATH="$SCRIPT_DIR/.tools/npm-global/bin:$PATH"
    export OMNIX_AGENT_MCPORTER_COMMAND="$SCRIPT_DIR/.tools/npm-global/bin/mcporter"
fi

# Cleanup existing server processes
echo "[Cleanup] Killing existing server processes on ports 5000 and 8000..."
kill $(lsof -ti:5000) 2>/dev/null
kill $(lsof -ti:8000) 2>/dev/null
sleep 2
echo "[Cleanup] Done."

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
    "$RPG_STT_PYTHON" "$SCRIPT_DIR/parakeet_stt_server.py" &
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
"$RPG_FLUX_PYTHON" "$SCRIPT_DIR/app.py" &
CHATBOT_PID=$!

# Wait for chatbot
wait $CHATBOT_PID

# Cleanup when done
cleanup
