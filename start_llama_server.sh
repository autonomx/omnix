#!/bin/bash
# Startup script for llama.cpp server in Docker

echo "Looking for GGUF models in /app/models/llm/..."

# Find the first GGUF model file
MODEL_PATH=""
for f in /app/models/llm/*.gguf; do
    if [ -f "$f" ]; then
        MODEL_PATH="$f"
        echo "Found model: $MODEL_PATH"
        break
    fi
done

if [ -z "$MODEL_PATH" ]; then
    echo "No GGUF model found in /app/models/llm/"
    echo "llama.cpp server will not start (no model available)"
    exit 0
fi

echo "Starting llama.cpp server with model: $MODEL_PATH"

# Start llama.cpp server
python -m llama_cpp.server \
    --host 0.0.0.0 \
    --port 8180 \
    --model "$MODEL_PATH" \
    --n_gpu_layers 999 \
    &
    
echo "llama.cpp server started in background"
