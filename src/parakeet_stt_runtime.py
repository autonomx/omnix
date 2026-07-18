"""Optimized Parakeet entrypoint for Omnix live voice."""
from __future__ import annotations

import asyncio
import os

import uvicorn

import parakeet_stt_legacy_server as legacy
from app.providers.stt_live_runtime_support import warm_model
from app.providers.stt_live_websocket import install_live_stt_websocket

install_live_stt_websocket(legacy)
app = legacy.app


@app.on_event("startup")
async def warm_live_model_on_startup() -> None:
    await asyncio.to_thread(warm_model, legacy.model, device=str(legacy.device))


def main() -> None:
    backend = legacy._validate_websocket_support()
    port = int(os.environ.get("OMNIX_STT_PORT", "5201"))
    print(f"[STT] WebSocket backend: {backend}")
    print(f"[STT] Starting optimized Parakeet server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
