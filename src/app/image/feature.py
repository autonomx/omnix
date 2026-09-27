"""Image feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.image_contracts import ImageGenerateInput
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule

from .jobs import execute_image_job


def _execute(context: JobExecutionContext, job):
    return execute_image_job(context.job_store, job)


FEATURE = FeatureModule(
    id="image",
    title="Images",
    job_handlers=(
        JobHandlerSpec(
            type="image.generate",
            handler=_execute,
            input_model=ImageGenerateInput,
            resource_class=ResourceClass.GPU_IMAGE,
            timeout_seconds=600,
            max_attempts=3,
        ),
    ),
)
