"""Thin FastAPI gateway foundation for the Omnix web app redesign."""
from __future__ import annotations

from typing import Any

from .assistant_context_routes import install_assistant_context_route_hook
from .audiobook_streaming import install_audiobook_websocket_hook
from .hermes_routes import install_hermes_route_hook
from .live_voice_diagnostics_routes import install_live_voice_diagnostics_hook
from .realtime_routes import install_realtime_route_hook
from .rpg_session_routes import install_rpg_session_route_hook
from .rpg_turn_job_mirror import install_rpg_turn_job_mirror_hook
from .tts_pcm_websocket import install_tts_pcm_websocket_hook
from .tts_runtime_routes import install_tts_runtime_route_hook

__all__ = ["app", "create_gateway_app"]

install_assistant_context_route_hook()
install_rpg_session_route_hook()
install_rpg_turn_job_mirror_hook()
install_audiobook_websocket_hook()
install_hermes_route_hook()
install_realtime_route_hook()
install_live_voice_diagnostics_hook()
install_tts_runtime_route_hook()
install_tts_pcm_websocket_hook()


def __getattr__(name: str) -> Any:
    """Load the gateway app lazily to keep lightweight submodule imports safe."""
    if name in __all__:
        from .main import app, create_gateway_app

        return {"app": app, "create_gateway_app": create_gateway_app}[name]
    raise AttributeError(name)
