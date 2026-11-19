"""Assistant tools feature declaration."""
from app.capabilities.executor import LIVE_AGENT_TOOLS
from app.platform.chat.contracts import CHAT_CALL_ACTIONS
from app.runtime.features import FeatureModule
from app.runtime.ports import ContributionSpec
from .executor import CAPABILITY_RUNTIME_CONTRIBUTION
from .routes import create_assistant_tool_internal_router, create_assistant_tool_router


def _assistant_tools_router(_context):
    return create_assistant_tool_router()


def _assistant_tools_internal_router(_context):
    return create_assistant_tool_internal_router()


def _live_agent_tools(_context):
    from .live_agent_proposals import AssistantLiveAgentTools

    return AssistantLiveAgentTools()


def _call_actions(_context):
    from .voice_actions import AssistantCallActions

    return AssistantCallActions()


FEATURE = FeatureModule(
    id="assistant-tools",
    title="Assistant Tools",
    tier="platform",
    # Chat's live agent plans with these tools through its LIVE_AGENT_TOOLS port (PA-1.3).
    depends_on=("chat",),
    routers=(_assistant_tools_router,),
    internal_routers=(_assistant_tools_internal_router,),
    # Contributes the runtime behind app.capabilities.executor (WP-4.5), and a live call's actions through
    # chat's CHAT_CALL_ACTIONS port.
    contributions=(CAPABILITY_RUNTIME_CONTRIBUTION, ContributionSpec(LIVE_AGENT_TOOLS, _live_agent_tools),
                   ContributionSpec(CHAT_CALL_ACTIONS, _call_actions)),
)
