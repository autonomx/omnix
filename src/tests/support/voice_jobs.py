"""Run a Voice Studio job the way the worker does: the voice feature's spec for its type, through the registry."""
from __future__ import annotations

from typing import Any, cast

from app.jobs.handlers import JobExecutionContext, JobHandlerRegistry, JobHandlerSpec
from app.jobs.models import JobRecord
from app.platform.voice.feature import FEATURE


def execute_voice_studio_job(job_store: Any, job: JobRecord) -> JobRecord:
    spec = next(spec for spec in FEATURE.job_handlers if spec.type == job.type)
    registry = JobHandlerRegistry((cast(JobHandlerSpec, spec),))
    return registry.execute(JobExecutionContext(job_store=job_store), job)
