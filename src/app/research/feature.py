"""Research feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule

from .jobs import DeepResearchJobInput, execute_research_job


def _execute(context: JobExecutionContext, job):
    return execute_research_job(context.job_store, job)


FEATURE = FeatureModule(
    id="research",
    title="Research",
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
