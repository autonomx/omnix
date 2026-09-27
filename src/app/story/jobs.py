"""Story and podcast job contracts owned by the Story feature."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import JobRecord


class StoryGenerateInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    premise: str
    title: str | None = None
    generate_title: bool = False
    provider_id: str | None = None
    model_id: str | None = None
    source_text: str | None = None
    user_response: str | None = None
    action: str = "draft"
    interaction_mode: str = "writing"


class PodcastGenerateInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    brief: str
    title: str | None = None
    speakers: list[str] = Field(default_factory=lambda: ["Host", "Guest"])
    provider_id: str | None = None
    model_id: str | None = None


def execute_story_job(job_store: Any, job: JobRecord) -> JobRecord:
    # The implementation remains behavior-identical while ownership moves.
    from app.jobs.inline_feature_jobs import execute_inline_feature_job

    return execute_inline_feature_job(job_store, job)
