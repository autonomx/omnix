"""Ordered application-owned feature registration, with no constructor hooks."""

from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class GatewayFeature:
    module: str
    registrar: str


FEATURES = (
    GatewayFeature("app.assistant_tools.routes", "register_assistant_tool_routes"),
    GatewayFeature("app.assistant_tools.openapi", "configure_assistant_tools_openapi"),
    GatewayFeature("app.gateway.rpg_turn_job_mirror", "_install_middleware"),
    GatewayFeature(
        "app.gateway.live_sse_transport", "_register_live_chat_sse_route_execution"
    ),
    GatewayFeature(
        "app.gateway.live_voice_runtime_offload", "register_live_voice_runtime_offload"
    ),
    GatewayFeature("app.gateway.agent_runtime_routes", "register_agent_runtime_routes"),
    GatewayFeature("app.gateway.research_mode_routes", "register_research_mode_routes"),
    GatewayFeature("app.gateway.trading_routes", "register_trading_routes"),
    GatewayFeature("app.gateway.rpg_debug_routes", "register_rpg_debug_routes"),
    GatewayFeature(
        "app.gateway.rpg_geometry_patch_routes", "register_rpg_geometry_patch_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_grid_performance_routes",
        "register_rpg_grid_performance_routes",
    ),
    GatewayFeature(
        "app.gateway.rpg_map_editor_routes", "register_rpg_map_editor_routes"
    ),
    GatewayFeature("app.gateway.rpg_map_routes", "register_rpg_map_routes"),
    GatewayFeature(
        "app.gateway.rpg_world_bundle_routes", "register_rpg_world_bundle_routes"
    ),
    GatewayFeature("app.gateway.rpg_world_routes", "register_rpg_world_routes"),
    GatewayFeature(
        "app.gateway.rpg_world_generation_review_routes",
        "register_rpg_world_generation_review_routes",
    ),
    GatewayFeature(
        "app.gateway.rpg_world_deletion_routes", "register_rpg_world_deletion_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_world_authoring_routes", "register_rpg_world_authoring_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_world_dossier_routes", "register_rpg_world_dossier_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_world_image_routes", "register_rpg_world_image_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_world_profile_routes", "register_rpg_world_profile_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_progressive_map_routes", "register_rpg_progressive_map_routes"
    ),
    GatewayFeature(
        "app.gateway.rpg_npc_spatial_routes", "register_rpg_npc_spatial_routes"
    ),
    GatewayFeature("app.gateway.rpg_observer_routes", "register_rpg_observer_routes"),
    GatewayFeature(
        "app.gateway.rpg_tactical_spatial_routes",
        "register_rpg_tactical_spatial_routes",
    ),
    GatewayFeature("app.gateway.rpg_session_routes", "register_rpg_session_routes"),
    GatewayFeature("app.gateway.audiobook_streaming", "register_audiobook_websocket"),
    GatewayFeature("app.audiobook.routes", "register_audiobook_routes"),
    GatewayFeature("app.gateway.hermes_routes", "register_hermes_routes"),
    GatewayFeature("app.gateway.realtime_routes", "register_realtime_routes"),
    GatewayFeature(
        "app.gateway.live_material_context", "register_live_material_context_routes"
    ),
    GatewayFeature(
        "app.gateway.live_observation_generation",
        "register_live_observation_generation_routes",
    ),
    GatewayFeature(
        "app.gateway.live_voice_diagnostics_routes",
        "register_live_voice_diagnostics_routes",
    ),
    GatewayFeature(
        "app.gateway.live_voice_cue_asset_routes",
        "register_live_voice_cue_asset_routes",
    ),
    GatewayFeature(
        "app.gateway.event_loop_lag_monitor", "register_event_loop_lag_monitor"
    ),
    GatewayFeature(
        "app.gateway.blocking_route_offload", "register_blocking_route_offload"
    ),
    GatewayFeature("app.gateway.tts_runtime_routes", "register_tts_runtime_routes"),
    GatewayFeature("app.gateway.tts_pcm_websocket", "register_tts_pcm_websocket"),
    GatewayFeature(
        "app.gateway.tts_live_call_websocket", "register_tts_live_call_websocket"
    ),
    GatewayFeature(
        "app.gateway.live_voice_speculative_tts",
        "register_live_voice_execution_lane_routes",
    ),
    GatewayFeature(
        "app.gateway.voice_job_summary_routes", "register_voice_job_summary_routes"
    ),
    GatewayFeature("app.gateway.voice_library_routes", "register_voice_library_route"),
    GatewayFeature("app.gateway.image_asset_routes", "register_image_asset_file_route"),
    GatewayFeature(
        "app.gateway.image_reference_routes", "register_image_reference_routes"
    ),
    GatewayFeature(
        "app.gateway.image_workspace_routes", "register_image_workspace_routes"
    ),
    GatewayFeature(
        "app.research.credential_routes", "register_research_credential_routes"
    ),
)


def register_gateway_features(gateway):
    if getattr(gateway.state, "features_registered", False):
        return
    for feature in FEATURES:
        getattr(import_module(feature.module), feature.registrar)(gateway)
    gateway.state.features_registered = True
