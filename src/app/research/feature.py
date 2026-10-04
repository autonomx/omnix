"""Research feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.research.persistence.report_repository import PostgresResearchReportRepository
from app.persistence.repository_registry import RepositorySpec
from app.runtime.features import FeatureModule
from app.runtime.features import FeatureContext
from .credential_routes import create_research_credential_router

from .jobs import DeepResearchJobInput, execute_research_job


def _execute(context: JobExecutionContext, job):
    chat_store = getattr(context.services, "chat", None) if context.services is not None else None
    return execute_research_job(context.job_store, job, chat_store=chat_store)



def _research_router(_context: FeatureContext):
    from fastapi import APIRouter

    router = APIRouter()
    router.include_router(create_research_credential_router())
    return router

FEATURE = FeatureModule(
    id="research",
    title="Research",
    tier="platform",
    # Deep research is asked for in chat and answers into chat sessions, and chat
    # reaches research only through research.contracts (WP-8.2).
    depends_on=("chat",),
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
