"""Parent/child agent authority narrowing and aggregate budget reservation."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .contracts import (
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
    ResourceScope,
    RunLimits,
    SuccessCriterion,
    WorkspaceSpec,
)


class ChildRunRequest(BaseModel):
    task: str
    objective: str = ""
    provider_id: str | None = None
    model_id: str | None = None
    reasoning_effort: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    external_capabilities: list[str] = Field(default_factory=list)
    resource_scopes: list[ResourceScope] | None = None
    success_criteria: list[str] = Field(default_factory=list)
    limits: RunLimits | None = None


def derive_child_spec(parent: AgentRunSnapshot, request: ChildRunRequest) -> AgentRunSpec:
    parent_spec = parent.spec
    local = list(dict.fromkeys(request.capabilities))
    external = list(dict.fromkeys(request.external_capabilities))
    if not set(local).issubset(set(parent_spec.capabilities)):
        raise ValueError("child local capabilities exceed parent authority")
    if not set(external).issubset(set(parent_spec.external_capabilities)):
        raise ValueError("child external capabilities exceed parent authority")

    scopes = list(request.resource_scopes if request.resource_scopes is not None else parent_spec.resource_scopes)
    _validate_scopes(parent_spec.resource_scopes, scopes)
    limits = request.limits or _default_child_limits(parent_spec.limits)
    _validate_limits(parent_spec.limits, limits)

    provider_id = request.provider_id or parent_spec.model.provider_id
    model_id = request.model_id or parent_spec.model.model_id
    effort = request.reasoning_effort if request.reasoning_effort is not None else parent_spec.model.reasoning_effort

    workspace = _child_workspace(parent_spec.workspace, local)
    return AgentRunSpec(
        session_id=parent_spec.session_id,
        parent_run_id=parent.run_id,
        task=request.task,
        objective=request.objective or request.task,
        success_criteria=[
            SuccessCriterion(id=f"child-criterion-{index + 1}", description=value)
            for index, value in enumerate(request.success_criteria)
        ],
        runtime=parent_spec.runtime,
        profile=parent_spec.profile,
        model=ModelRef(
            provider_id=provider_id,
            model_id=model_id,
            reasoning_effort=effort,
        ),
        capabilities=local,
        resource_scopes=scopes,
        external_capabilities=external,
        workspace=workspace,
        execution=parent_spec.execution,
        limits=limits,
        approval_policy=parent_spec.approval_policy,
        context_sources=list(parent_spec.context_sources),
        artifact_policy=parent_spec.artifact_policy,
        expected_artifacts=["diff"] if any(item in {"workspace.edit", "workspace.write"} for item in local) else [],
        persistence_policy=parent_spec.persistence_policy,
    )


def reserve_child_budget(
    parent: AgentRunSnapshot,
    existing_children: list[AgentRunSnapshot],
    child: AgentRunSpec,
    *,
    parent_usage: dict[str, object] | None = None,
) -> None:
    limits = parent.spec.limits
    usage = parent_usage or {}
    children = [item.spec.limits for item in existing_children]
    _bounded_sum(
        "max_steps",
        limits.max_steps,
        [int(usage.get("steps", 0)), *[item.max_steps for item in children], child.limits.max_steps],
    )
    _bounded_sum(
        "max_tool_calls",
        limits.max_tool_calls,
        [int(usage.get("tool_calls", 0)), *[item.max_tool_calls for item in children], child.limits.max_tool_calls],
    )
    _bounded_sum(
        "max_wall_time_seconds",
        limits.max_wall_time_seconds,
        [item.max_wall_time_seconds for item in children] + [child.limits.max_wall_time_seconds],
    )
    if limits.max_tokens is not None:
        _bounded_sum(
            "max_tokens",
            limits.max_tokens,
            [
                int(usage.get("output_tokens", 0)),
                *[item.max_tokens or 0 for item in children],
                child.limits.max_tokens or 0,
            ],
        )
    if limits.max_cost is not None:
        _bounded_sum(
            "max_cost",
            limits.max_cost,
            [
                float(usage.get("cost", 0.0)),
                *[item.max_cost or 0 for item in children],
                child.limits.max_cost or 0,
            ],
        )


def _default_child_limits(parent: RunLimits) -> RunLimits:
    return RunLimits(
        max_steps=max(1, min(50, parent.max_steps // 4 or 1)),
        max_wall_time_seconds=max(1, min(900, parent.max_wall_time_seconds // 4 or 1)),
        max_tokens=max(1, parent.max_tokens // 4) if parent.max_tokens is not None else None,
        max_cost=parent.max_cost / 4 if parent.max_cost is not None else None,
        max_tool_calls=max(1, min(100, parent.max_tool_calls // 4 or 1)),
    )


def _validate_limits(parent: RunLimits, child: RunLimits) -> None:
    if child.max_steps > parent.max_steps:
        raise ValueError("child max_steps exceeds parent")
    if child.max_tool_calls > parent.max_tool_calls:
        raise ValueError("child max_tool_calls exceeds parent")
    if child.max_wall_time_seconds > parent.max_wall_time_seconds:
        raise ValueError("child wall time exceeds parent")
    if parent.max_tokens is not None and (child.max_tokens is None or child.max_tokens > parent.max_tokens):
        raise ValueError("child token budget exceeds parent")
    if parent.max_cost is not None and (child.max_cost is None or child.max_cost > parent.max_cost):
        raise ValueError("child cost budget exceeds parent")


def _validate_scopes(parent: list[ResourceScope], child: list[ResourceScope]) -> None:
    if parent and not child:
        raise ValueError("child resource scopes cannot remove parent restrictions")
    if not child:
        return
    parent_keys = {
        (row.capability, row.resource_type, row.resource_id, tuple(sorted(row.constraints.items())))
        for row in parent
    }
    for row in child:
        key = (row.capability, row.resource_type, row.resource_id, tuple(sorted(row.constraints.items())))
        if key not in parent_keys:
            raise ValueError("child resource scope is not an exact/narrow parent scope")


def _child_workspace(parent: WorkspaceSpec | None, capabilities: list[str]) -> WorkspaceSpec | None:
    if parent is None:
        return None
    mutating = any(item in {"workspace.edit", "workspace.write", "workspace.command", "workspace.test"} for item in capabilities)
    if not mutating:
        return parent
    if not parent.repository:
        raise ValueError("mutating child requires a repository-backed parent workspace")
    # A mutating child gets its own worktree at the parent's base ref. It never
    # races writes in the parent's worktree; artifacts remain owned by child run.
    return WorkspaceSpec(
        root=parent.repository,
        repository=parent.repository,
        base_ref=parent.base_ref,
        isolation_policy=parent.isolation_policy,
        allowed_paths=list(parent.allowed_paths),
        forbidden_paths=list(parent.forbidden_paths),
    )


def _bounded_sum(name: str, maximum, values) -> None:
    if sum(values) > maximum:
        raise ValueError(f"aggregate child {name} budget exceeds parent")
