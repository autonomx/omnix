"""Thin FastAPI gateway foundation for the Omnix web app redesign."""
from __future__ import annotations

from typing import Any

from .assistant_context_routes import install_assistant_context_route_hook
from .audiobook_streaming import install_audiobook_websocket_hook
from .blocking_route_offload import install_blocking_route_offload_hook
from .event_loop_lag_monitor import install_event_loop_lag_monitor_hook
from .hermes_routes import install_hermes_route_hook
from .image_asset_routes import install_image_asset_file_hook
from .image_reference_routes import install_image_reference_route_hook
from .image_workspace_routes import install_image_workspace_route_hook
from .live_chat_postgres_fast_path import install_live_chat_postgres_fast_path
from .live_chat_provider_metrics import install_live_chat_provider_metrics_hook
from .live_chat_stream_retry import install_live_chat_stream_retry_hook
from .live_voice_diagnostics_routes import install_live_voice_diagnostics_hook
from .live_voice_runtime_offload import install_live_voice_runtime_offload_hook
from .realtime_routes import install_realtime_route_hook
from .research_mode_routes import install_research_mode_route_hook
from .rpg_debug_routes import install_rpg_debug_route_hook
from .rpg_geometry_patch_routes import install_rpg_geometry_patch_route_hook
from .rpg_grid_performance_routes import install_rpg_grid_performance_route_hook
from .rpg_map_editor_routes import install_rpg_map_editor_route_hook
from .rpg_map_routes import install_rpg_map_route_hook
from .rpg_npc_spatial_routes import install_rpg_npc_spatial_route_hook
from .rpg_observer_routes import install_rpg_observer_route_hook
from .rpg_progressive_map_routes import install_rpg_progressive_map_route_hook
from .rpg_session_routes import install_rpg_session_route_hook
from .rpg_tactical_spatial_routes import install_rpg_tactical_spatial_route_hook
from .rpg_turn_job_mirror import install_rpg_turn_job_mirror_hook
from .rpg_world_bundle_routes import install_rpg_world_bundle_route_hook
from .rpg_world_routes import install_rpg_world_route_hook
from .tts_live_call_websocket import install_tts_live_call_websocket_hook
from .tts_pcm_websocket import install_tts_pcm_websocket_hook
from .tts_runtime_routes import install_tts_runtime_route_hook
from .voice_job_summary_routes import install_voice_job_summary_hook

__all__ = ["app", "create_gateway_app"]


def _install_required_rpg_turn_hooks() -> None:
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session.dialogue_quality_hook import install_dialogue_quality_hook
    from app.rpg.session.fast_visible_dialogue_hook import install_fast_visible_dialogue_hook
    from app.rpg.session.interaction_lifecycle_hook import install_interaction_lifecycle_hook
    from app.rpg.session.interaction_timeline_hook import install_interaction_timeline_hook

    install_fast_visible_dialogue_hook()
    install_dialogue_quality_hook()
    install_interaction_timeline_hook()
    install_interaction_lifecycle_hook()
    if not getattr(interactive_first_call_runtime, "_omnix_fast_visible_dialogue_hook_installed", False):
        raise RuntimeError("RPG fast visible dialogue hook failed to install")
    if not getattr(interactive_first_call_runtime, "_omnix_dialogue_quality_hook_installed", False):
        raise RuntimeError("RPG dialogue quality hook failed to install")
    if not getattr(interactive_first_call_runtime, "_omnix_interaction_timeline_hook_installed", False):
        raise RuntimeError("RPG interaction timeline hook failed to install")
    if not getattr(interactive_first_call_runtime, "_omnix_interaction_lifecycle_runtime_hook_installed", False):
        raise RuntimeError("RPG interaction lifecycle runtime hook failed to install")
    install_rpg_turn_job_mirror_hook()


install_assistant_context_route_hook()
install_research_mode_route_hook()
install_rpg_debug_route_hook()
install_rpg_geometry_patch_route_hook()
install_rpg_grid_performance_route_hook()
install_rpg_map_editor_route_hook()
install_rpg_map_route_hook()
install_rpg_world_bundle_route_hook()
install_rpg_world_route_hook()
install_rpg_progressive_map_route_hook()
install_rpg_npc_spatial_route_hook()
install_rpg_observer_route_hook()
install_rpg_tactical_spatial_route_hook()
install_rpg_session_route_hook()
install_audiobook_websocket_hook()
install_hermes_route_hook()
install_realtime_route_hook()
install_live_chat_postgres_fast_path()
install_live_chat_provider_metrics_hook()
install_live_chat_stream_retry_hook()
install_live_voice_diagnostics_hook()
install_event_loop_lag_monitor_hook()
install_blocking_route_offload_hook()
install_live_voice_runtime_offload_hook()
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
