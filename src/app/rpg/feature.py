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


FEATURE = FeatureModule(
    id="rpg",
    title="RPG",
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
