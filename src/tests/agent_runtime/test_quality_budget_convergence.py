from __future__ import annotations

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, RunLimits
from app.agent_runtime.service import _quality_sized_run_spec


def _spec(*, policy: str = "strict", limits: RunLimits | None = None, profile: str = "coding") -> AgentRunSpec:
    kwargs = {} if limits is None else {"limits": limits}
    return AgentRunSpec(
        task="Fix a coding bug",
        profile=profile,
        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna"),
        expected_artifacts=["diff"] if profile == "coding" else [],
        quality_policy=policy,
        **kwargs,
    )


def test_implicit_strict_coding_budget_supports_review_repair_rereview_cycle() -> None:
    sized = _quality_sized_run_spec(_spec())
    assert sized.limits.max_steps == 500
    assert sized.limits.max_tool_calls == 1250


def test_quality_budget_scales_by_policy() -> None:
    assert _quality_sized_run_spec(_spec(policy="standard")).limits.max_steps == 350
    assert _quality_sized_run_spec(_spec(policy="critical")).limits.max_steps == 750


def test_explicit_limits_remain_authoritative_even_when_equal_to_generic_defaults() -> None:
    explicit = RunLimits()
    sized = _quality_sized_run_spec(_spec(limits=explicit))
    assert sized.limits == explicit
    assert sized.limits.max_steps == 200


def test_non_coding_and_quality_off_runs_keep_generic_defaults() -> None:
    noncoding = _quality_sized_run_spec(_spec(profile="research"))
    assert noncoding.limits.max_steps == 200
    off = _quality_sized_run_spec(_spec(policy="off"))
    assert off.limits.max_steps == 200
