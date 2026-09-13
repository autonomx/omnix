#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OMNIX_REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$OMNIX_REPO_ROOT"

echo "Starting OpenAI Compatible API Server..."
echo "========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed or not in PATH. Please install Python first."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements if needed
echo "Installing/updating requirements..."
pip install -r requirements.txt

# Start the OpenAI API server
echo "Starting OpenAI Compatible API Server on port 8001..."
echo "Access the API at: http://localhost:8001"
echo "API endpoints:"
echo "  - /v1/models (list models)"
echo "  - /v1/audio/voices (list voices)"
echo "  - /v1/audio/speech (generate speech)"
echo "  - /v1/chat/completions (chat completions)"
echo "  - /health (health check)"
echo
echo "Press Ctrl+C to stop the server"
echo "========================================="

python3 src/openai_api.py
