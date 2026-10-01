"""Agent runtime feature declaration."""
from app.runtime.background import BackgroundWorker
from app.runtime.capabilities import RuntimeCapability
from app.runtime.features import FeatureContext, FeatureModule
from .routes import create_agent_runtime_router
from .jobs import AGENT_RUN_JOB_HANDLERS


def _supervisor_worker(context: FeatureContext) -> BackgroundWorker | None:
    if not context.capabilities.allows(RuntimeCapability.RUN_JOB_WORKERS):
        return None
    service = getattr(context.services, "agent_runs", None)
    if service is None:
        raise RuntimeError("Agent runtime service is not composed")

    def startup() -> None:
        service.start_supervisor()

    def shutdown() -> None:
        service.stop_supervisor()

    return BackgroundWorker(
        name="agent-runtime-supervisor",
        monitor=service,
        startup=(startup,),
        shutdown=(shutdown,),
        requires=frozenset({RuntimeCapability.RUN_JOB_WORKERS}),
    )


FEATURE = FeatureModule(
    id="agent-runtime",
    title="Agent Runtime",
    routers=(create_agent_runtime_router,),
    job_handlers=AGENT_RUN_JOB_HANDLERS,
    background_workers=(_supervisor_worker,),
)
