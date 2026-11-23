"""A run's authority is issued in one place: the process policy, the limits, the narrowing to a parent and the
checks run together, and no start path assembles them itself."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.platform.agent_runtime.contracts import AgentRunSnapshot, AgentRunSpec, ModelRef, RunLimits
from app.platform.agent_runtime.run_issuance import bind_run_workspace, issue_child_spec, issue_run_spec
from app.platform.agent_runtime.subagents import ChildRunRequest

RUNTIME = Path(__file__).parents[2] / "app" / "platform" / "agent_runtime"


class _Service:
    """The service steps the issuer calls, recorded in order."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.refuse = refuse

    def _prepare_start_spec(self, spec: AgentRunSpec) -> AgentRunSpec:
        self.calls.append(("prepare", spec.run_id))
        return spec.model_copy(update={"model": ModelRef(provider_id="resolved", model_id="resolved")})

    def _validate_run_spec_authority(self, spec: AgentRunSpec) -> None:
        self.calls.append(("authority", spec.model.provider_id))
        if self.refuse:
            raise ValueError("run_spec_exceeds_profile_ceiling")

    def _validate_evidence_authority(self, spec: AgentRunSpec) -> None:
        self.calls.append(("evidence", spec.run_id))

    def _bind_github_repository_authority(self, spec: AgentRunSpec) -> AgentRunSpec:
        self.calls.append(("github", spec.run_id))
        return spec

    def _prepare_workspace(self, spec: AgentRunSpec) -> AgentRunSpec:
        self.calls.append(("workspace", spec.run_id))
        return spec


def _parent() -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="parent",
        task="Implement feature",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        capabilities=["workspace.read", "workspace.search"],
        limits=RunLimits(max_steps=100, max_wall_time_seconds=1000, max_tool_calls=200, max_tokens=10000, max_cost=4),
    )
    return AgentRunSnapshot(run_id="parent", spec=spec, status="running")


def test_a_run_is_checked_as_the_process_prepared_it() -> None:
    service = _Service()

    issued = issue_run_spec(service, AgentRunSpec(run_id="run", task="t", model=ModelRef(provider_id="p", model_id="m")))

    assert issued.model.provider_id == "resolved"
    assert service.calls == [("prepare", "run"), ("authority", "resolved"), ("evidence", "run")]


def test_a_refused_spec_is_not_issued() -> None:
    with pytest.raises(ValueError, match="ceiling"):
        issue_run_spec(_Service(refuse=True), AgentRunSpec(task="t", model=ModelRef(provider_id="p", model_id="m")))


def test_a_child_is_narrowed_to_its_parent_then_checked_under_the_id_its_caller_names() -> None:
    service = _Service()

    child = issue_child_spec(service, _parent(), ChildRunRequest(task="Inspect", capabilities=["workspace.read"]),
                             run_id="reviewer:slot-1")

    assert (child.run_id, child.parent_run_id, child.capabilities) == ("reviewer:slot-1", "parent", ["workspace.read"])
    assert service.calls == [("authority", "lmstudio"), ("evidence", "reviewer:slot-1")]


def test_a_child_asking_for_more_than_its_parent_holds_is_refused_before_any_check() -> None:
    service = _Service()

    with pytest.raises(ValueError, match="exceed parent authority"):
        issue_child_spec(service, _parent(), ChildRunRequest(task="Edit", capabilities=["workspace.edit"]))
    assert service.calls == []


def test_the_workspace_is_bound_after_the_github_authority() -> None:
    service = _Service()
    issued = issue_child_spec(service, _parent(), ChildRunRequest(task="Inspect", capabilities=["workspace.read"]))
    service.calls.clear()

    bind_run_workspace(service, issued)

    assert [name for name, _ in service.calls] == ["github", "workspace"]


def test_no_start_path_assembles_a_spec_outside_the_issuer() -> None:
    """The issuing steps are called through the service only by the issuer (the service's own delegators call
    the implementing module, not the service)."""
    steps = {"prepare": re.compile(r"\b(?:service|self)\._prepare_start_spec\("),
             "github": re.compile(r"\b(?:service|self)\._bind_github_repository_authority\("),
             "derive": re.compile(r"\bderive_child_spec\(")}
    owners: dict[str, set[str]] = {name: set() for name in steps}
    for path in RUNTIME.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name, pattern in steps.items():
            if pattern.search(source):
                owners[name].add(path.name)
    assert owners == {"prepare": {"run_issuance.py"}, "github": {"run_issuance.py"},
                      "derive": {"run_issuance.py", "subagents.py"}}
