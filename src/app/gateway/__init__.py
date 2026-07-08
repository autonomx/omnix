"""Thin FastAPI gateway foundation for the Omnix web app redesign."""
from __future__ import annotations

from typing import Any

from .assistant_context_routes import install_assistant_context_route_hook
from .audiobook_streaming import install_audiobook_websocket_hook
from .hermes_routes import install_hermes_route_hook
from .image_asset_routes import install_image_asset_file_hook
from .image_reference_routes import install_image_reference_route_hook
from .image_workspace_routes import install_image_workspace_route_hook
from .live_voice_diagnostics_routes import install_live_voice_diagnostics_hook
from .realtime_routes import install_realtime_route_hook
from .research_mode_routes import install_research_mode_route_hook
from .rpg_map_editor_routes import install_rpg_map_editor_route_hook
from .rpg_map_routes import install_rpg_map_route_hook
from .rpg_session_routes import install_rpg_session_route_hook
from .rpg_turn_job_mirror import install_rpg_turn_job_mirror_hook
from .tts_live_call_websocket import install_tts_live_call_websocket_hook
from .tts_pcm_websocket import install_tts_pcm_websocket_hook
from .tts_runtime_routes import install_tts_runtime_route_hook
from .voice_job_summary_routes import install_voice_job_summary_hook

__all__ = ["app", "create_gateway_app"]

install_assistant_context_route_hook()
install_research_mode_route_hook()
install_rpg_map_editor_route_hook()
install_rpg_map_route_hook()
install_rpg_session_route_hook()
install_rpg_turn_job_mirror_hook()
install_audiobook_websocket_hook()
install_hermes_route_hook()
install_realtime_route_hook()
install_live_voice_diagnostics_hook()
install_tts_runtime_route_hook()
install_tts_pcm_websocket_hook()
install_tts_live_call_websocket_hook()
install_voice_job_summary_hook()
install_image_asset_file_hook()
install_image_reference_route_hook()
install_image_workspace_route_hook()


def __getattr__(name: str) -> Any:
    """Load the gateway app lazily to keep lightweight submodule imports safe."""
    if name in __all__:
        from .main import app, create_gateway_app

        return {"app": app, "create_gateway_app": create_gateway_app}[name]
    raise AttributeError(name)
