#!/usr/bin/env python3
"""Download default GGUF model for Docker build"""
import os

try:
    from huggingface_hub import hf_hub_download
    
    # Download the Q4_K_M quantized model to models/llm
    filename = hf_hub_download(
        repo_id='TheBloke/Mistral-7B-Instruct-v0.2-GGUF',
        filename='mistral-7b-instruct-v0.2.Q4_K_M.gguf',
        local_dir='/app/models/llm'
    )
    
    # Rename to simple name
    src = filename
    dst = '/app/models/llm/mistral-7b-instruct-v0.2.Q4_K_M.gguf'
    if src != dst:
        import shutil
        shutil.move(src, dst)
    print(f'Model downloaded to: {dst}')
except Exception as e:
    print(f'Error downloading model: {e}')
