"""Chat and realtime feature declaration."""
from app.runtime.features import FeatureModule
from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    install_registrars(
        gateway,
        context,
        (
            ("app.gateway.live_sse_transport", "_register_live_chat_sse_route_execution"),
            ("app.gateway.realtime_routes", "register_realtime_routes"),
            ("app.gateway.live_material_context", "register_live_material_context_routes"),
            ("app.gateway.live_observation_generation", "register_live_observation_generation_routes"),
        ),
    )


FEATURE = FeatureModule(
    id="chat",
    title="Chat and Realtime",
    installers=(_install_gateway,),
)
