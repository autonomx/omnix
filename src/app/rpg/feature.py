"""RPG feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule

from .jobs.handlers import (
    RpgReportJobInput,
    RpgTurnJobInput,
    execute_rpg_report_job,
    execute_rpg_turn_job,
)


def _turn(context: JobExecutionContext, job):
    return execute_rpg_turn_job(context.job_store, job)


def _report(context: JobExecutionContext, job):
    return execute_rpg_report_job(context.job_store, job)



from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    install_registrars(
        gateway,
        context,
        (
            ("app.gateway.rpg_turn_job_mirror", "_install_middleware"),
            ("app.gateway.rpg_debug_routes", "register_rpg_debug_routes"),
            ("app.gateway.rpg_geometry_patch_routes", "register_rpg_geometry_patch_routes"),
            ("app.gateway.rpg_grid_performance_routes", "register_rpg_grid_performance_routes"),
            ("app.gateway.rpg_map_editor_routes", "register_rpg_map_editor_routes"),
            ("app.gateway.rpg_map_routes", "register_rpg_map_routes"),
            ("app.gateway.rpg_world_bundle_routes", "register_rpg_world_bundle_routes"),
            ("app.gateway.rpg_world_routes", "register_rpg_world_routes"),
            ("app.gateway.rpg_world_generation_review_routes", "register_rpg_world_generation_review_routes"),
            ("app.gateway.rpg_world_deletion_routes", "register_rpg_world_deletion_routes"),
            ("app.gateway.rpg_world_authoring_routes", "register_rpg_world_authoring_routes"),
            ("app.gateway.rpg_world_dossier_routes", "register_rpg_world_dossier_routes"),
            ("app.gateway.rpg_world_image_routes", "register_rpg_world_image_routes"),
            ("app.gateway.rpg_world_profile_routes", "register_rpg_world_profile_routes"),
            ("app.gateway.rpg_progressive_map_routes", "register_rpg_progressive_map_routes"),
            ("app.gateway.rpg_npc_spatial_routes", "register_rpg_npc_spatial_routes"),
            ("app.gateway.rpg_observer_routes", "register_rpg_observer_routes"),
            ("app.gateway.rpg_tactical_spatial_routes", "register_rpg_tactical_spatial_routes"),
            ("app.gateway.rpg_session_routes", "register_rpg_session_routes"),
            ("app.gateway.hermes_routes", "register_hermes_routes"),
        ),
    )

FEATURE = FeatureModule(
    id="rpg",
    title="RPG",
    installers=(_install_gateway,),
    job_handlers=(
        JobHandlerSpec(
            type="rpg.turn",
            handler=_turn,
            input_model=RpgTurnJobInput,
            resource_class=ResourceClass.GPU_LLM,
            timeout_seconds=900,
        ),
        JobHandlerSpec(
            type="rpg.report.last10",
            handler=_report,
            input_model=RpgReportJobInput,
            resource_class=ResourceClass.CPU,
            timeout_seconds=120,
        ),
    ),
)
