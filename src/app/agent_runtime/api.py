"""HTTP API for durable generalized agent runs."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .contracts import (
    AgentApproval,
    AgentArtifact,
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
    SuccessCriterion,
    WorkspaceSpec,
)
from .profiles import get_agent_profile, resolve_profile_capabilities
from .subagents import ChildRunRequest
from .service import AgentRunService, default_agent_run_service

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runtime"])


class StartAgentRunRequest(BaseModel):
    task: str
    objective: str = ""
    provider_id: str
    model_id: str
    reasoning_effort: str | None = None
    profile: str = "coding"
    repository: str | None = None
    workspace_root: str | None = None
    base_ref: str = "main"
    isolation_policy: str = "supervised_worktree"
    capabilities: list[str] | None = None
    external_capabilities: list[str] | None = None
    success_criteria: list[str] = Field(default_factory=list)


class AgentCommandRequest(BaseModel):
    command_type: Literal["steer", "pause", "resume", "cancel", "approve", "reject"]
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = None


def _service() -> AgentRunService:
    return default_agent_run_service()


@router.post("", response_model=AgentRunSnapshot)
def start_agent_run(request: StartAgentRunRequest) -> AgentRunSnapshot:
    try:
        profile = get_agent_profile(request.profile)
        issued_capabilities, issued_external = resolve_profile_capabilities(
            profile, requested=request.capabilities,
            requested_external=request.external_capabilities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    root = request.workspace_root or request.repository
    if profile.requires_workspace and not root:
        raise HTTPException(status_code=422, detail="repository or workspace_root is required for this profile")
    spec = AgentRunSpec(
        task=request.task,
        objective=request.objective,
        profile=request.profile,
        model=ModelRef(
            provider_id=request.provider_id,
            model_id=request.model_id,
            reasoning_effort=request.reasoning_effort,
        ),
        capabilities=issued_capabilities,
        external_capabilities=issued_external,
        context_sources=list(profile.context_sources),
        workspace=(
            WorkspaceSpec(
                root=str(root), repository=request.repository, base_ref=request.base_ref,
                isolation_policy=request.isolation_policy,
            )
            if root else WorkspaceSpec(root=".", isolation_policy=request.isolation_policy, allowed_paths=[])
        ),
        success_criteria=[
            SuccessCriterion(id=f"criterion-{index + 1}", description=value)
            for index, value in enumerate(request.success_criteria)
        ],
        expected_artifacts=["diff"] if profile.requires_workspace else [],
    )
    try:
        return _service().start(spec)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"agent_start_failed:{type(exc).__name__}:{exc}") from exc


@router.post("/{run_id}/children", response_model=AgentRunSnapshot)
def start_child_agent_run(run_id: str, request: ChildRunRequest) -> AgentRunSnapshot:
    try:
        return _service().start_child(run_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=AgentRunSnapshot)
def get_agent_run(run_id: str) -> AgentRunSnapshot:
    snapshot = _service().get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    return snapshot


@router.post("/{run_id}/commands", response_model=AgentRunSnapshot)
def command_agent_run(run_id: str, request: AgentCommandRequest) -> AgentRunSnapshot:
    try:
        return _service().command(
            AgentRunCommand(
                run_id=run_id,
                command_type=request.command_type,
                payload=request.payload,
                **({"idempotency_key": request.idempotency_key} if request.idempotency_key else {}),
            )
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc


@router.get("/{run_id}/events", response_model=list[AgentEvent])
def list_agent_events(run_id: str, after_sequence: int = 0) -> list[AgentEvent]:
    return _service().events(run_id, after_sequence=max(0, after_sequence))


@router.get("/{run_id}/approvals", response_model=list[AgentApproval])
def list_agent_approvals(run_id: str, state: str | None = None) -> list[AgentApproval]:
    if _service().get(run_id) is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    return _service().approvals(run_id, state=state)


@router.get("/{run_id}/artifacts", response_model=list[AgentArtifact])
def list_agent_artifacts(run_id: str) -> list[AgentArtifact]:
    return _service().artifacts(run_id)


@router.get("/{run_id}/events/stream")
async def stream_agent_events(run_id: str, after_sequence: int = 0) -> StreamingResponse:
    if _service().get(run_id) is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")

    async def generate():
        sequence = max(0, after_sequence)
        idle = 0
        while True:
            rows = await asyncio.to_thread(_service().events, run_id, after_sequence=sequence)
            if rows:
                idle = 0
                for event in rows:
                    sequence = max(sequence, int(event.sequence or 0))
                    yield f"id: {sequence}\nevent: {event.event_type}\ndata: {json.dumps(event.model_dump(mode='json'), sort_keys=True)}\n\n"
                snapshot = await asyncio.to_thread(_service().get, run_id)
                if snapshot and snapshot.status in {"completed", "failed", "cancelled"}:
                    return
            else:
                idle += 1
                if idle % 15 == 0:
                    yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")
