"""Research feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.persistence.module_repositories import PostgresResearchReportRepository
from app.persistence.repository_registry import RepositorySpec
from app.runtime.features import FeatureModule

from .jobs import DeepResearchJobInput, execute_research_job


def _execute(context: JobExecutionContext, job):
    chat_store = getattr(context.services, "chat", None) if context.services is not None else None
    return execute_research_job(context.job_store, job, chat_store=chat_store)



from app.runtime.router_composition import compose_registrar_router


def _research_router(context):
    return compose_registrar_router(
        (
            ("app.gateway.research_mode_routes", "register_research_mode_routes"),
            ("app.research.credential_routes", "register_research_credential_routes"),
        ),
        state=context.runtime_state,
    )

FEATURE = FeatureModule(
    id="research",
    title="Research",
    routers=(_research_router,),
    repositories=(
        RepositorySpec(PostgresResearchReportRepository, PostgresResearchReportRepository, "research_reports"),
    ),
    job_handlers=(
        JobHandlerSpec(
            type="assistant.deep_research",
            handler=_execute,
            input_model=DeepResearchJobInput,
            resource_class=ResourceClass.NETWORK,
            timeout_seconds=1800,
            max_attempts=3,
        ),
    ),
)
