"""Agent runtime feature declaration."""
from app.runtime.features import FeatureModule
from .routes import create_agent_runtime_router


FEATURE = FeatureModule(
    id="agent-runtime",
    title="Agent Runtime",
    routers=(create_agent_runtime_router,),
)
