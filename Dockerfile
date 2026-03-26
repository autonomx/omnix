# Omnix Dockerfile
# Use NVIDIA CUDA devel image for GPU support (includes CUDA toolkit for building)
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Python 3.10 and system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-venv \
    python3-pip \
    cmake \
    build-essential \
    libsndfile1 \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set python3.10 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Set working directory
WORKDIR /app

# Install PyTorch with CUDA 12.4 support FIRST (critical for version matching)
# Using PyTorch 2.5.1 as 2.6.0 may not be available in all regions
# Install torchmetrics from PyPI first to avoid torchvision compatibility issues
RUN pip install --no-cache-dir torchmetrics==1.4.2
RUN pip install --no-cache-dir \
    torch==2.5.1+cu124 \
    torchvision==0.20.1+cu124 \
    torchaudio==2.5.1+cu124 \
    --index-url https://download.pytorch.org/whl/cu124

# Force reinstall torchaudio to ensure it's properly linked
# (nemo may have installed an incompatible version)
RUN pip install --no-cache-dir torchaudio==2.5.1+cu124 --force-reinstall --index-url https://download.pytorch.org/whl/cu124

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies (excluding torch - already installed)
RUN pip install --no-cache-dir -r requirements.txt || true

# Install NeMo ASR for Parakeet STT
RUN pip install --no-cache-dir "nemo_toolkit[asr]"

# Install compatible transformers version
# (nemo_toolkit installs transformers 4.53+ which breaks LlamaModel import)
# Must be installed AFTER nemo to override its version
# Also need to pin tokenizers to compatible version
RUN pip install --no-cache-dir transformers==4.46.3 tokenizers==0.20.3 --force-reinstall

# Force reinstall ALL torch packages together to fix C++ operator linking
# nemo_toolkit breaks the torch library links, must reinstall all three together
RUN pip install --no-cache-dir \
    torch==2.6.0+cu124 \
    torchvision==0.21.0+cu124 \
    torchaudio==2.6.0+cu124 \
    --force-reinstall --index-url https://download.pytorch.org/whl/cu124

# Fix numpy and other dependencies for compatibility
RUN pip install --no-cache-dir numpy==1.25.2 safetensors==0.5.3 fsspec==2024.12.0 pillow==11.0.0 --force-reinstall

# Pre-download Parakeet TDT 0.6B model
RUN python -c "\
from nemo.collections.asr.models import ASRModel; \
ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v2'); \
print('Parakeet model downloaded!')"

# Create directories for models
RUN mkdir -p /app/models/llm /app/models/server

# Copy download scripts FIRST (before running them)
COPY download_model_docker.py /app/download_model_docker.py
COPY download_llamacpp_docker.py /app/download_llamacpp_docker.py

# Download default GGUF model to models/llm
RUN pip install --no-cache-dir huggingface-hub && \
    python /app/download_model_docker.py

# Install llama-cpp-python for LLM inference (includes pre-compiled binaries)
# This is faster than building from source
RUN pip install --no-cache-dir llama-cpp-python sse-starlette starlette-context pydantic-settings --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

# Copy application files
COPY . .

# Create directories
RUN mkdir -p /app/data

# Make startup scripts executable
RUN chmod +x /app/start_llama_server.sh

# Expose ports
# 5000: Main Flask app
# 8000: STT server (Parakeet)
# 8080: llama.cpp server
EXPOSE 5000 8000 8080

# Set environment variables
ENV FLASK_APP=app.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Default command - run main app
CMD ["python", "app.py"]

# ============================================================================
# USAGE INSTRUCTIONS
# ============================================================================
# After building and running the container:
#
# 1. Build the image:
#    docker build -t omnix .
#
# 2. Start the container:
#    docker-compose up -d
#
# 3. Check container status:
#    docker ps
#
# 4. View logs:
#    docker-compose logs -f
#
# 5. Access the application:
#    - Main app: http://localhost:5000
#    - STT server: http://localhost:8000
#
# 6. Stop the container:
#    docker-compose down
#
# Note: On first run, the Parakeet STT model (~600MB) will be downloaded.
# Check logs for progress.
# ============================================================================
