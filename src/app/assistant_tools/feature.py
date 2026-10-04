"""Assistant tools feature declaration."""
from app.runtime.features import FeatureModule
from .executor import CAPABILITY_RUNTIME_HOOK
from .routes import create_assistant_tool_internal_router, create_assistant_tool_router


def _assistant_tools_router(_context):
    return create_assistant_tool_router()


def _assistant_tools_internal_router(_context):
    return create_assistant_tool_internal_router()


FEATURE = FeatureModule(
    id="assistant-tools",
    title="Assistant Tools",
    # Chat's live agent and assist mode use these tools through app.assistant_tools.contracts.
    depends_on=("chat",),
    routers=(_assistant_tools_router,),
    internal_routers=(_assistant_tools_internal_router,),
    # Installs the runtime behind app.capabilities.executor (WP-4.5).
    hooks=(CAPABILITY_RUNTIME_HOOK,),
)
