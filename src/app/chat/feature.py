"""Chat feature declaration."""
from app.runtime.features import FeatureModule
from app.chat.persistence.repository_specs import CHAT_REPOSITORY_SPECS
from app.runtime.router_composition import APIRouterHost


def _chat_context_router(context):
    from app.persistence.runtime import uses_postgresql_runtime
    from app.assistant_context import register_assistant_context_routes
    from .live_material_context import create_live_material_context_router
    from .live_observation_generation import create_live_observation_generation_router

    if uses_postgresql_runtime():
        from app.chat.persistence.legacy_sessions import install_postgresql_legacy_session_callbacks
        install_postgresql_legacy_session_callbacks()

    host = APIRouterHost(state=context.runtime_state)
    host.include_router(create_live_material_context_router(context.runtime_state))
    host.include_router(create_live_observation_generation_router(context.runtime_state))
    services = context.services
    register_assistant_context_routes(
        host,
        chat_store_factory=lambda: services.chat,
        job_store_factory=lambda: services.jobs,
    )
    return host.router


FEATURE = FeatureModule(
    id="chat",
    title="Chat and Realtime",
    routers=(_chat_context_router,),
    repositories=CHAT_REPOSITORY_SPECS,
)
