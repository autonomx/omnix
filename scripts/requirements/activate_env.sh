#!/bin/bash

# ============================================
# Omnix - Virtual Environment Activation Script
# ============================================

echo "============================================="
echo "Omnix - Virtual Environment Activation"
echo "============================================="
echo ""

# Resolve the repository root so this helper can live under scripts/requirements/.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OMNIX_REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
cd "$OMNIX_REPO_ROOT"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
    echo "Virtual environment activated!"
    echo "You can now run: python app.py"
    echo "To deactivate: deactivate"
    echo ""
    echo "Starting bash shell with virtual environment..."
    exec bash
else
    echo "ERROR: Virtual environment not found!"
    echo "Please run: ./setup.sh"
    echo "Then try again."
    exit 1
fi
