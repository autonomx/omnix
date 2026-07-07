"""Durable Deep Research job construction and stage contracts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.jobs.models import CreateJobRequest, JobStage, ResourceClass

from .contracts import RESEARCH_JOB_MODULE, RESEARCH_JOB_TYPE


class DeepResearchJobInput(BaseModel):
    session_id: str
    user_message_id: str
    question: str
    provider_id: str | None = None
    model_id: str | None = None
    research_provider: str = "duckduckgo"
    source_manifest_id: str | None = None
    max_steps: int = Field(default=6, ge=1, le=12)
    max_queries: int = Field(default=5, ge=1, le=10)
    max_sources: int = Field(default=12, ge=1, le=30)
    max_extracts: int = Field(default=8, ge=0, le=20)
    search_cache_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    extraction_cache_ttl_seconds: int = Field(default=3600, ge=1, le=604800)
    hermes_planner_enabled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def deep_research_stages(
    *,
    planner_resource: ResourceClass = ResourceClass.CPU,
    synthesis_resource: ResourceClass = ResourceClass.NETWORK,
) -> list[JobStage]:
    return [
        JobStage(id="planning", label="Planning research", resource_class=planner_resource),
        JobStage(id="searching", label="Searching the web", resource_class=ResourceClass.NETWORK),
        JobStage(id="extracting", label="Reviewing sources", resource_class=ResourceClass.NETWORK),
        JobStage(id="evaluating", label="Comparing evidence", resource_class=ResourceClass.CPU),
        JobStage(id="synthesizing", label="Writing the answer", resource_class=synthesis_resource),
        JobStage(id="persisting", label="Saving the result", resource_class=ResourceClass.CPU),
    ]


def create_deep_research_job_request(
    payload: DeepResearchJobInput,
    *,
    planner_resource: ResourceClass = ResourceClass.CPU,
    synthesis_resource: ResourceClass = ResourceClass.NETWORK,
) -> CreateJobRequest:
    return CreateJobRequest(
        owner_id=payload.session_id,
        module=RESEARCH_JOB_MODULE,
        type=RESEARCH_JOB_TYPE,
        resource_class=ResourceClass.NETWORK,
        stages=deep_research_stages(
            planner_resource=planner_resource,
            synthesis_resource=synthesis_resource,
        ),
        input_payload=payload.model_dump(mode="json"),
        compat={"contract": "assistant_deep_research_v1"},
    )
