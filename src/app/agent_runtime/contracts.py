"""Runtime-neutral contracts for Omnix workflows and open-ended agents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

AgentRunStatus = Literal[
    "queued",
    "starting",
    "running",
    "pause_requested",
    "paused",
    "waiting_for_approval",
    "resume_requested",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
]
AgentDesiredState = Literal["running", "paused", "cancelled"]
AgentCommandType = Literal["steer", "pause", "resume", "cancel", "approve", "reject"]
AgentEventType = Literal[
    "run.created",
    "run.started",
    "run.status",
    "run.completed",
    "run.failed",
    "model.message",
    "tool.requested",
    "tool.started",
    "tool.output",
    "tool.completed",
    "approval.requested",
    "approval.resolved",
    "artifact.created",
    "steering.received",
    "acceptance.started",
    "acceptance.completed",
    "worker.heartbeat",
]
AgentApprovalState = Literal["pending", "approved", "rejected", "expired"]
ArtifactKind = Literal["diff", "test_result", "log", "report", "file", "other"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str
    model_id: str
    reasoning_effort: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ResourceScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: str
    resource_type: str
    resource_id: str
    constraints: dict[str, Any] = Field(default_factory=dict)


class SuccessCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    description: str
    required: bool = True


class AcceptancePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_commands: list[list[str]] = Field(default_factory=list)
    allowed_modified_paths: list[str] = Field(default_factory=list)
    forbidden_modified_paths: list[str] = Field(default_factory=list)
    required_artifacts: list[ArtifactKind] = Field(default_factory=list)
    require_diff: bool = False
    checks: list[str] = Field(default_factory=list)


class WorkspaceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: str
    repository: str | None = None
    base_ref: str = "main"
    worktree: str | None = None
    isolation_policy: str = "supervised_worktree"
    allowed_paths: list[str] = Field(default_factory=lambda: ["**"])
    forbidden_paths: list[str] = Field(default_factory=list)


class ExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_policy: str = "safe-development"
    network_policy: str = "broker-only"
    environment_policy: str = "minimal"
    allowed_environment_keys: list[str] = Field(default_factory=list)


class RunLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_steps: int = Field(default=200, ge=1, le=10_000)
    max_wall_time_seconds: int = Field(default=3600, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    max_cost: float | None = Field(default=None, ge=0)
    max_tool_calls: int = Field(default=500, ge=1, le=100_000)


class AgentRunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str | None = None
    parent_run_id: str | None = None
    task: str
    objective: str = ""
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    runtime: str = "pi"
    profile: str = "coding"
    model: ModelRef
    capabilities: list[str] = Field(default_factory=list)
    resource_scopes: list[ResourceScope] = Field(default_factory=list)
    external_capabilities: list[str] = Field(default_factory=list)
    workspace: WorkspaceSpec | None = None
    execution: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    limits: RunLimits = Field(default_factory=RunLimits)
    approval_policy: str = "ask_sensitive"
    context_sources: list[str] = Field(default_factory=list)
    artifact_policy: str = "metadata_in_postgres_blobs_external"
    expected_artifacts: list[ArtifactKind] = Field(default_factory=list)
    persistence_policy: str = "postgresql"
    acceptance_plan: AcceptancePlan | None = None


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    sequence: int | None = None
    event_type: AgentEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    kind: ArtifactKind
    name: str
    storage_ref: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AgentApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    capability_id: str
    state: AgentApprovalState = "pending"
    request_payload: dict[str, Any] = Field(default_factory=dict)
    resolution_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


class AgentRunCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    command_type: AgentCommandType
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=utc_now)


class AgentRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    spec: AgentRunSpec
    status: AgentRunStatus = "queued"
    desired_state: AgentDesiredState = "running"
    revision: int = 1
    worker_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkerLease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    worker_id: str
    lease_token: str
    lease_expires_at: datetime
    heartbeat_at: datetime
    revision: int
