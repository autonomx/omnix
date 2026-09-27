"""Image feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.image_contracts import ImageGenerateInput
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule

from .jobs import execute_image_job


def _execute(context: JobExecutionContext, job):
    return execute_image_job(context.job_store, job)



from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    install_registrars(
        gateway,
        context,
        (
            ("app.gateway.image_asset_routes", "register_image_asset_file_route"),
            ("app.gateway.image_reference_routes", "register_image_reference_routes"),
            ("app.gateway.image_workspace_routes", "register_image_workspace_routes"),
        ),
    )

FEATURE = FeatureModule(
    id="image",
    title="Images",
    installers=(_install_gateway,),
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
