"""Ordered application-owned feature registration, with no constructor hooks."""

from dataclasses import dataclass
import logging
from importlib import import_module
from collections.abc import Callable

from app.runtime.background import register_background_worker
from app.runtime.capabilities import RuntimeCapability
from app.runtime.feature_catalog import enabled_feature_ids, load_feature
from app.runtime.features import FeatureContext, FeatureLifecycle


@dataclass(frozen=True, slots=True)
class GatewayFeature:
    module: str
    registrar: str
    requires: frozenset[RuntimeCapability] = frozenset({RuntimeCapability.SERVE_API})



def register_feature_lifecycle(gateway, feature: FeatureLifecycle):
    capabilities = getattr(gateway.state, 'runtime_capabilities', None)
    if capabilities is not None:
        capabilities.require(*feature.requires)
    lifecycles = getattr(gateway.state, 'feature_lifecycles', None)
    if lifecycles is None:
        # Standalone router/test compositions retain their FastAPI lifecycle.
        for callback in feature.startup:
            gateway.router.add_event_handler('startup', callback)
        for callback in feature.shutdown:
            gateway.router.add_event_handler('shutdown', callback)
        return
    if any(item.name == feature.name for item in lifecycles):
        raise ValueError(f'Feature lifecycle already registered: {feature.name}')
    lifecycles.append(feature)


FEATURES = (
    GatewayFeature("app.assistant_tools.routes", "register_assistant_tool_routes"),
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
    GatewayFeature("app.gateway.stt_proxy_routes", "register_stt_proxy_routes"),
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



def _register_feature_modules(gateway) -> None:
    config = gateway.state.runtime_config
    capabilities = gateway.state.runtime_capabilities
    services = getattr(gateway.state, "runtime_services", None)
    registry = getattr(gateway.state, "background_registry", None)
    registered: list[str] = []

    for feature_id in enabled_feature_ids(config):
        feature = load_feature(feature_id)
        capabilities.require(*feature.requires)
        context = FeatureContext(
            feature_id=feature.id,
            config=None,
            runtime=config,
            capabilities=capabilities,
            services=services,
            logger=logging.getLogger(f"app.feature.{feature.id}"),
        )
        for router_factory in feature.routers:
            gateway.include_router(router_factory(context))
        for router_factory in feature.internal_routers:
            gateway.include_router(router_factory(context))
        for worker_factory in feature.background_workers:
            register_background_worker(registry, worker_factory(context))
        if feature.lifecycle is not None:
            register_feature_lifecycle(gateway, feature.lifecycle)
        registered.append(feature.id)

    gateway.state.feature_modules = tuple(registered)


def register_gateway_features(gateway):
    if getattr(gateway.state, "features_registered", False):
        return
    _register_feature_modules(gateway)
    for feature in FEATURES:
        capabilities = getattr(gateway.state, 'runtime_capabilities', None)
        if capabilities is not None:
            capabilities.require(*feature.requires)
        legacy_hooks = (len(gateway.router.on_startup), len(gateway.router.on_shutdown))
        getattr(import_module(feature.module), feature.registrar)(gateway)
        if capabilities is not None and legacy_hooks != (len(gateway.router.on_startup), len(gateway.router.on_shutdown)):
            raise RuntimeError(f'Feature {feature.module} must declare lifecycle callbacks with FeatureLifecycle or BackgroundWorker')
    gateway.state.features_registered = True
