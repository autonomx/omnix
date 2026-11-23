"""Run an image job the way the worker does: the image feature's spec, through the job registry."""
from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import Any, cast

from app.jobs.handlers import JobExecutionContext, JobHandlerRegistry, JobHandlerSpec
from app.jobs.models import JobRecord
from app.platform.image.feature import FEATURE
from app.platform.image.jobs import run_image_job


def execute_image_job(job_store: Any, job: JobRecord, **options: Any) -> JobRecord:
    """``options`` are ``run_image_job``'s: a ``generate_fn`` and an ``asset_store`` in place of the real ones."""
    spec = cast(JobHandlerSpec, FEATURE.job_handlers[0])
    spec = replace(spec, run=partial(run_image_job, **options))
    return JobHandlerRegistry((spec,)).execute(JobExecutionContext(job_store=job_store), job)
