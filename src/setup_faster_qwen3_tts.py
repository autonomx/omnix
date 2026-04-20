#!/usr/bin/env python3
"""
Setup script for FasterQwen3TTS integration.

This script helps users:
1. Install the faster-qwen3-tts library
2. Download the Qwen3-TTS model
3. Set up reference audio files
4. Configure the system for optimal performance
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description=""):
    """Run a command and handle errors."""
    print(f"Running: {cmd}")
    if description:
        print(f"Description: {description}")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ Success: {description}")
        if result.stdout:
            print(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {description}")
        print(f"Error: {e.stderr}")
        return False

def install_faster_qwen3_tts():
    """No-op: Omnix now uses vendored Qwen3-TTS in the dedicated rpg-tts environment."""
    print("Skipping pip install of faster-qwen3-tts (vendored runtime is used instead).")
    return True

def install_dependencies():
    """Install additional dependencies."""
    print("Installing additional dependencies...")
    
    deps = [
        "soundfile",
        "numpy",
        "scipy",  # For high-quality resampling
        "librosa"  # Fallback resampler
    ]
    
    for dep in deps:
        run_command(f"pip install {dep}", f"Installing {dep}")
    
    # Install CUDA-enabled PyTorch for RTX 4090 compatibility
    print("Installing CUDA-enabled PyTorch for optimal performance...")
    run_command("pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 --index-url https://download.pytorch.org/whl/cu124", "Installing CUDA-enabled PyTorch")

def setup_reference_audio():
    """Set up reference audio files for voice cloning."""
    print("Setting up reference audio files...")
    
    # Create voice_clones directory in resources
    base_dir = Path(__file__).parent
    resources_dir = base_dir / "resources" / "voice_clones"
    resources_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy reference audio files from faster-qwen3-tts
    ref_audio_dir = base_dir / "resources" / "models" / "tts" / "faster-qwen3-tts-main"
    ref_audio_files = ["ref_audio.wav", "ref_audio_2.wav", "ref_audio_3.wav"]
    
    for ref_file in ref_audio_files:
        src = ref_audio_dir / ref_file
        dst = resources_dir / ref_file
        if src.exists():
            shutil.copy2(src, dst)
            print(f"✓ Copied {ref_file} to voice_clones directory")
        else:
            print(f"⚠ Warning: {ref_file} not found in {ref_audio_dir}")
    
    # Create a default reference audio from the first available file
    default_ref = resources_dir / "default_ref.wav"
    if not default_ref.exists():
        for ref_file in ref_audio_files:
            src = resources_dir / ref_file
            if src.exists():
                shutil.copy2(src, default_ref)
                print(f"✓ Created default reference audio: {default_ref}")
                break

def update_settings():
    """Update the settings to use faster-qwen3-tts as default."""
    print("Updating settings to use faster-qwen3-tts as default...")
    
    settings_file = Path(__file__).parent / "resources" / "data" / "settings.json"
    
    # Create data directory if it doesn't exist
    settings_file.parent.mkdir(exist_ok=True)
    
    # Load existing settings or create default
    if settings_file.exists():
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        except:
            settings = {}
    else:
        settings = {}
    
    # Update TTS provider settings
    settings['audio_provider_tts'] = 'faster-qwen3-tts'
    
    # Add faster-qwen3-tts configuration if not present
    if 'faster-qwen3-tts' not in settings:
        settings['faster-qwen3-tts'] = {
            "model_name": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            "device": "cuda",
            "dtype": "bfloat16",
            "max_seq_len": 2048,
            "chunk_size": 12,
            "temperature": 0.9,
            "top_k": 50,
            "top_p": 1.0,
            "do_sample": True,
            "repetition_penalty": 1.05,
            "xvec_only": True,
            "non_streaming_mode": True,
            "append_silence": True
        }
    
    # Save settings
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
    
    print("✓ Updated settings.json to use faster-qwen3-tts")

def check_cuda():
    """Check if CUDA is available."""
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✓ CUDA is available. Device: {torch.cuda.get_device_name(0)}")
            return True
        else:
            print("⚠ CUDA is not available. Using CPU (will be slower).")
            return False
    except ImportError:
        print("⚠ PyTorch not installed. Please install PyTorch with CUDA support.")
        return False

def main():
    """Main setup function."""
    print("Setting up FasterQwen3TTS integration for Omnix...")
    print("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 10):
        print("✗ Python 3.10+ is required. Please upgrade your Python version.")
        sys.exit(1)
    
    print(f"✓ Python version: {sys.version}")
    
    # Check CUDA availability
    cuda_available = check_cuda()
    
    # Install dependencies
    install_dependencies()
    
    # Install faster-qwen3-tts
    if not install_faster_qwen3_tts():
        print("✗ Failed to install faster-qwen3-tts. Please check your internet connection and try again.")
        sys.exit(1)
    
    # Set up reference audio
    setup_reference_audio()
    
    # Update settings
    update_settings()
    
    print("\n" + "=" * 60)
    print("🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Start the Omnix application")
    print("2. The system will automatically use faster-qwen3-tts as the default TTS provider")
    print("3. You can create custom voice clones using the web interface")
    print("4. For optimal performance, ensure you have a CUDA-compatible GPU")
    
    if not cuda_available:
        print("\n⚠ Note: CUDA is not available. TTS generation will be slower on CPU.")
        print("Consider installing PyTorch with CUDA support for better performance.")
    
    print("\n📖 For more information, see:")
    print("  - faster-qwen3-tts documentation: https://github.com/andimarafioti/faster-qwen3-tts")
    print("  - Qwen3-TTS models: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base")

if __name__ == "__main__":
    main()