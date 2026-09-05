from __future__ import annotations
import pytest

from app.agent_runtime.contracts import AgentRunSnapshot, AgentRunSpec, ModelRef, ResourceScope, RunLimits
from app.agent_runtime.subagents import ChildRunRequest, derive_child_spec, reserve_child_budget


def _parent() -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="parent",
        task="Implement feature",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        capabilities=["workspace.read", "workspace.search", "workspace.edit"],
        external_capabilities=["github.read_repo"],
        limits=RunLimits(max_steps=100, max_wall_time_seconds=1000, max_tool_calls=200, max_tokens=10000, max_cost=4),
    )
    return AgentRunSnapshot(run_id="parent", spec=spec, status="running")


def test_child_authority_can_only_narrow_parent() -> None:
    parent = _parent()
    child = derive_child_spec(parent, ChildRunRequest(task="Inspect", capabilities=["workspace.read"]))
    assert child.parent_run_id == "parent"
    assert child.capabilities == ["workspace.read"]
    with pytest.raises(ValueError):
        derive_child_spec(parent, ChildRunRequest(task="Merge", external_capabilities=["github.merge_pr"]))


def test_child_aggregate_budget_is_bounded_by_parent() -> None:
    parent = _parent()
    first = derive_child_spec(parent, ChildRunRequest(
        task="A", capabilities=["workspace.read"],
        limits=RunLimits(max_steps=60, max_wall_time_seconds=500, max_tool_calls=100, max_tokens=6000, max_cost=2),
    ))
    second = derive_child_spec(parent, ChildRunRequest(
        task="B", capabilities=["workspace.read"],
        limits=RunLimits(max_steps=50, max_wall_time_seconds=400, max_tool_calls=80, max_tokens=3000, max_cost=1),
    ))
    with pytest.raises(ValueError):
        reserve_child_budget(parent, [AgentRunSnapshot(run_id=first.run_id, spec=first)], second)


def test_child_cannot_drop_parent_resource_scope() -> None:
    parent = _parent().model_copy(
        update={
            "spec": _parent().spec.model_copy(
                update={
                    "resource_scopes": [
                        ResourceScope(
                            capability="github.read_repo",
                            resource_type="repository",
                            resource_id="autonomx/omnix",
                        )
                    ]
                }
            )
        }
    )
    with pytest.raises(ValueError, match="cannot remove parent restrictions"):
        derive_child_spec(
            parent,
            ChildRunRequest(
                task="Inspect broadly",
                external_capabilities=["github.read_repo"],
                resource_scopes=[],
            ),
        )


def test_child_reservation_accounts_for_parent_usage() -> None:
    parent = _parent()
    child = derive_child_spec(
        parent,
        ChildRunRequest(
            task="Budgeted child",
            capabilities=["workspace.read"],
            limits=RunLimits(
                max_steps=40,
                max_wall_time_seconds=300,
                max_tool_calls=40,
                max_tokens=3000,
                max_cost=1,
            ),
        ),
    )
    with pytest.raises(ValueError, match="aggregate child max_steps"):
        reserve_child_budget(
            parent,
            [],
            child,
            parent_usage={
                "steps": 70,
                "tool_calls": 0,
                "output_tokens": 0,
                "cost": 0,
            },
        )
