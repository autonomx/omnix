from __future__ import annotations

from itertools import product

import pytest

from app.agent_runtime.contracts import EvidencePolicy
from app.agent_runtime.evidence import (
    classify_evidence,
    compile_task_authority,
)
from app.agent_runtime.profiles import (
    get_agent_profile,
    list_agent_profiles,
    profile_external_ceiling,
    resolve_profile_capabilities,
)
from app.agent_runtime.subagents import ChildRunRequest, derive_child_spec
from app.agent_runtime.contracts import AgentRunSnapshot, AgentRunSpec, ModelRef


def test_compiled_authority_is_always_within_profile_ceiling() -> None:
    cases = [
        ("coding", "inspect and fix the parser tests", ("workspace_read", "workspace_mutate", "workspace_execute")),
        ("house", "check the bedroom lamp and turn it off", ("home_read", "home_mutate")),
        ("research", "research the latest Python release", ("research_read",)),
        ("personal-assistant", "check my calendar and schedule a meeting", ("calendar_read", "calendar_create")),
        ("trading-research", "research today's NVDA catalysts", ("market_read",)),
    ]
    for profile_id, task, actions in cases:
        profile = get_agent_profile(profile_id)
        decision = classify_evidence(task, profile_id=profile_id)
        compiled = compile_task_authority(
            profile,
            task,
            decision,
            semantic_action_intents=actions,
        )
        assert set(compiled.required_local) <= set(profile.capabilities)
        assert set(compiled.required_external) <= profile_external_ceiling(profile)


def test_no_profile_can_accept_capabilities_from_another_profile_ceiling() -> None:
    profiles = list_agent_profiles()
    for left, right in product(profiles, profiles):
        if left.id == right.id:
            continue
        foreign_local = set(right.capabilities) - set(left.capabilities)
        foreign_external = profile_external_ceiling(right) - profile_external_ceiling(left)
        if foreign_local:
            capability = sorted(foreign_local)[0]
            with pytest.raises(ValueError):
                resolve_profile_capabilities(
                    left,
                    requested=[capability],
                    requested_external=[],
                )
        if foreign_external:
            capability = sorted(foreign_external)[0]
            with pytest.raises(ValueError):
                resolve_profile_capabilities(
                    left,
                    requested=[],
                    requested_external=[capability],
                )


def test_external_access_forbidden_never_compiles_external_capability() -> None:
    prompts = [
        ("research", "Explain PostgreSQL releases from memory only"),
        ("trading-research", "Explain stock splits from memory only"),
        ("personal-assistant", "Explain what a calendar invite is from memory only"),
        ("house", "Explain what a thermostat is from memory only"),
    ]
    for profile_id, prompt in prompts:
        decision = classify_evidence(prompt, profile_id=profile_id)
        assert decision.policy.external_access == "forbidden"
        if decision.policy.requirement == "none":
            compiled = compile_task_authority(
                get_agent_profile(profile_id),
                prompt,
                decision,
            )
            assert compiled.required_external == ()


def test_child_authority_is_monotonic_subset_of_parent() -> None:
    parent_spec = AgentRunSpec(
        run_id="parent",
        task="inspect",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=[
            "workspace.read",
            "workspace.search",
            "workspace.command",
            "workspace.test",
        ],
        external_capabilities=["github.read_repo", "github.inspect_ci"],
    )
    parent = AgentRunSnapshot(run_id="parent", spec=parent_spec, status="running")

    local_subsets = [
        [],
        ["workspace.read"],
        ["workspace.read", "workspace.search"],
        ["workspace.command", "workspace.test"],
    ]
    external_subsets = [
        [],
        ["github.read_repo"],
        ["github.inspect_ci"],
        ["github.read_repo", "github.inspect_ci"],
    ]
    for local, external in product(local_subsets, external_subsets):
        child = derive_child_spec(
            parent,
            ChildRunRequest(
                task="child task",
                capabilities=local,
                external_capabilities=external,
            ),
        )
        assert set(child.capabilities) <= set(parent.spec.capabilities)
        assert set(child.external_capabilities) <= set(
            parent.spec.external_capabilities
        )


def test_model_output_cannot_create_authority_when_policy_has_no_grant() -> None:
    profile = get_agent_profile("research")
    decision = compile_task_authority(
        profile,
        "Explain TCP congestion control",
        decision=type("Decision", (), {
            "policy": EvidencePolicy(requirement="none"),
            "confidence": 1.0,
            "reason": "test",
            "classifier": "deterministic",
        })(),
        semantic_action_intents=(),
    )
    assert decision.required_local == ()
    assert decision.required_external == ()


def test_read_only_trading_profile_never_contains_order_execution() -> None:
    ceiling = profile_external_ceiling(get_agent_profile("trading-research"))
    assert not {
        "broker.place_order",
        "broker.cancel_order",
        "trading.place_order",
        "trading.cancel_order",
    }.intersection(ceiling)
