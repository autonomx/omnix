#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OMNIX_REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$OMNIX_REPO_ROOT"

echo "Starting OpenAI Compatible API Server..."
echo "========================================="

# Check if Python 3.11 is installed
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11 is not installed or not in PATH. Please install Python 3.11 first."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements if needed
echo "Installing/updating requirements..."
python -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version'
if [ $? -ne 0 ]; then
    echo "The existing venv must use Python 3.11. Remove it and rerun this launcher."
    exit 1
fi
python -m pip install --require-hashes -r requirements.txt

# Start the OpenAI API server
echo "Starting OpenAI Compatible API Server on port 8101 by default..."
echo "Access the API at: http://localhost:8101"
echo "API endpoints:"
echo "  - /v1/models (list models)"
echo "  - /v1/audio/voices (list voices)"
echo "  - /v1/audio/speech (generate speech)"
echo "  - /v1/chat/completions (chat completions)"
echo "  - /health (health check)"
echo
echo "Press Ctrl+C to stop the server"
echo "========================================="

python src/openai_api.py
