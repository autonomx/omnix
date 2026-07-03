"""Gateway entrypoint with live speech realtime routes mounted.

This keeps the existing gateway untouched while the realtime live-speech router
is reviewed and hardened.
"""
from __future__ import annotations

from app.gateway.main import create_gateway_app
from app.live_speech.api_stub import create_live_speech_router


app = create_gateway_app()
app.include_router(create_live_speech_router())
