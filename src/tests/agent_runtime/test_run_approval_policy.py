from __future__ import annotations

from pathlib import Path

from app.agent_runtime.contracts import AgentRunSpec, ModelRef


def test_run_approval_policy_is_typed() -> None:
    spec = AgentRunSpec(
        task="inspect",
        model=ModelRef(provider_id="test", model_id="model"),
        approval_policy="always_ask",
    )
    assert spec.approval_policy == "always_ask"


def test_broker_passes_run_policy_to_canonical_gate() -> None:
    source = (
        Path(__file__).parents[2]
        / "app"
        / "agent_runtime"
        / "broker_api.py"
    ).read_text(encoding="utf-8")
    assert "approval_policy=snapshot.spec.approval_policy" in source
