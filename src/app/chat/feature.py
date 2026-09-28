"""Chat and realtime feature declaration."""
from app.persistence.repository_registry import RepositorySpec
from app.runtime.features import FeatureModule
from app.chat.persistence.repository import PostgresChatRepository
from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.chat.persistence.legacy_sessions import install_postgresql_legacy_session_callbacks
        install_postgresql_legacy_session_callbacks()
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
    repositories=(RepositorySpec(PostgresChatRepository, PostgresChatRepository, "chats"),),
)
