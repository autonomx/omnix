"""Assistant tools feature declaration."""
from app.runtime.features import FeatureModule
from app.runtime.router_composition import compose_registrar_router


def _assistant_tools_router(context):
    return compose_registrar_router(
        (("app.assistant_tools.routes", "register_assistant_tool_routes"),),
        state=context.runtime_state,
    )


def _assistant_tools_internal_router(context):
    return compose_registrar_router(
        (("app.assistant_tools.routes", "register_assistant_tool_internal_routes"),),
        state=context.runtime_state,
    )


FEATURE = FeatureModule(
    id="assistant-tools",
    title="Assistant Tools",
    routers=(_assistant_tools_router,),
    internal_routers=(_assistant_tools_internal_router,),
)
