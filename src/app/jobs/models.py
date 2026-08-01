"""Typed shared job/run contract for the web platform."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema


class JobStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    STALE = "stale"


class ResourceClass(str, Enum):
    CPU = "cpu"
    GPU_LLM = "gpu:llm"
    GPU_TTS = "gpu:tts"
    GPU_STT = "gpu:stt"
    GPU_IMAGE = "gpu:image"
    NETWORK = "network"
    RPG_CAMPAIGN_GENESIS = "rpg_campaign_genesis"
    RPG_WORLD_GENERATION = "rpg_world_generation"
    RPG_MAP_MATERIALIZATION = "rpg_map_materialization"

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Keep repository-only RPG worker queues out of public job creation docs."""

        schema = handler(core_schema)
        if isinstance(schema.get("enum"), list):
            hidden = {
                cls.RPG_WORLD_GENERATION.value,
                cls.RPG_MAP_MATERIALIZATION.value,
            }
            schema["enum"] = [member.value for member in cls if member.value not in hidden]
        return schema


TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.STALE,
}


class JobProgress(BaseModel):
    current: int = 0
    total: int = 1
    message: str | None = None


class JobError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class RetryState(BaseModel):
    attempts: int = 0
    max_attempts: int = 0
    policy: str = "none"


class JobStage(BaseModel):
    id: str
    label: str
    status: JobStatus = JobStatus.QUEUED
    resource_class: ResourceClass
    progress: JobProgress = Field(default_factory=JobProgress)
    checkpoint_ref: dict[str, Any] | None = None
    output_refs: list[dict[str, Any]] = Field(default_factory=list)
    error: JobError | None = None
    started_at: str | None = None
    completed_at: str | None = None
    retry: RetryState = Field(default_factory=RetryState)


class JobLease(BaseModel):
    worker_id: str
    token: str
    claimed_at: str
    expires_at: str


class CancelState(BaseModel):
    requested: bool = False
    requested_at: str | None = None
    acknowledged_at: str | None = None
    reason: str | None = None


class CreateJobRequest(BaseModel):
    owner_id: str | None = None
    module: str
    type: str
    resource_class: ResourceClass
    priority: int = 0
    stages: list[JobStage] = Field(default_factory=list)
    input_ref: dict[str, Any] | None = None
    input_payload: dict[str, Any] | None = None
    compat: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def apply_central_defaults(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        module = str(value.get("module") or "").strip()
        raw_resource_class = value.get("resource_class")
        resource_class = str(getattr(raw_resource_class, "value", raw_resource_class) or "").strip()
        routed_value = dict(value)

        # ``owner_id`` is a legacy semantic owner in the shared job contract,
        # but PostgreSQL maps it to ``omnix_jobs.owner_user_id``. Character IDs
        # are not user IDs and therefore violate that foreign key. Preserve the
        # semantic owner in compatibility metadata and leave the durable user
        # owner unset so the PostgreSQL adapter uses the active tenant user.
        if module == "character-avatar":
            semantic_owner = str(routed_value.get("owner_id") or "").strip()
            if semantic_owner:
                compat = dict(routed_value.get("compat") or {})
                compat.setdefault("subject_owner_id", semantic_owner)
                routed_value["compat"] = compat
            routed_value["owner_id"] = None

        defaulted_modules = {
            "storyteller",
            "podcast",
            "voice",
            "voice-cloning",
            "stt",
            "image-generation",
            "character-avatar",
        }
        if module not in defaulted_modules and resource_class != ResourceClass.GPU_LLM.value:
            return routed_value
        routed_value["resource_class"] = resource_class
        if module == "voice-cloning":
            from app.platform.voice_cloning_defaults import apply_voice_cloning_defaults

            return apply_voice_cloning_defaults(routed_value)

        from app.platform.effective_defaults import apply_job_defaults

        return apply_job_defaults(routed_value)


class ClaimJobRequest(BaseModel):
    worker_id: str
    resource_classes: list[ResourceClass] = Field(default_factory=list)
    lease_seconds: int = Field(default=30, ge=1, le=3600)
    cpu_limit: int = Field(default=2, ge=1, le=64)


class ClaimJobResponse(BaseModel):
    ok: bool
    job: "JobRecord | None" = None
    reason: str | None = None


class CompleteJobRequest(BaseModel):
    output_refs: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[dict[str, Any]] = Field(default_factory=list)


class FailJobRequest(BaseModel):
    code: str = "job_failed"
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class CancelJobRequest(BaseModel):
    reason: str | None = None


class JobRecord(BaseModel):
    id: str
    owner_id: str | None = None
    module: str
    type: str
    status: JobStatus
    resource_class: ResourceClass
    priority: int = 0
    stages: list[JobStage] = Field(default_factory=list)
    progress: JobProgress = Field(default_factory=JobProgress)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    input_ref: dict[str, Any] | None = None
    input_payload: dict[str, Any] | None = None
    output_refs: list[dict[str, Any]] = Field(default_factory=list)
    error: JobError | None = None
    lease: JobLease | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    cancel: CancelState = Field(default_factory=CancelState)
    compat: dict[str, Any] = Field(default_factory=dict)


class JobListResponse(BaseModel):
    jobs: list[JobRecord]


class JobEventRecord(BaseModel):
    id: int
    job_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
