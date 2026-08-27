"""Deterministic workflow-domain contracts."""
from __future__ import annotations

from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

WorkflowStepKind = Literal["capability", "condition", "approval"]
WorkflowRunStatus = Literal["queued", "running", "paused", "waiting_for_approval", "completed", "failed", "cancelled"]


class WorkflowStepDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: WorkflowStepKind = "capability"
    capability_id: str | None = None
    input_template: dict[str, Any] = Field(default_factory=dict)
    condition: str | None = None
    retry_limit: int = Field(default=0, ge=0, le=20)
    timeout_seconds: int | None = Field(default=None, ge=1)
    requires_approval: bool = False


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int = Field(default=1, ge=1)
    name: str
    description: str = ""
    steps: list[WorkflowStepDefinition] = Field(default_factory=list)


class WorkflowRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    workflow_id: str
    workflow_version: int
    status: WorkflowRunStatus = "queued"
    current_step_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    revision: int = 1
