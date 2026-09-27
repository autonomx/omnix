"""RPG durable job contracts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.jobs.models import JobRecord


class RpgTurnJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    command: str
    provider_id: str | None = None
    model_id: str | None = None


class RpgReportJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")


def execute_rpg_turn_job(job_store: Any, job: JobRecord) -> JobRecord:
    from app.jobs.inline_feature_jobs import execute_inline_feature_job

    return execute_inline_feature_job(job_store, job)


def execute_rpg_report_job(job_store: Any, job: JobRecord) -> JobRecord:
    from app.jobs.rpg_last10_report import execute_rpg_last10_report_job

    return execute_rpg_last10_report_job(job_store, job)
