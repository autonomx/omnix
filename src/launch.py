#!/usr/bin/env python3
"""
Canonical Omnix FastAPI entrypoint.
This file is named launch.py specifically to avoid module name collision with src/app package.
"""

import sys
from pathlib import Path

# File now lives inside src/, so add this directory directly
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from run_app import HOST, PORT, app


def create_app():
    return app


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Omnix FastAPI Server - Ultra Low Latency")
    print("=" * 50)
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/conversation")
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/tts")
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/audiobook")
    print("=" * 50 + "\n")

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )