from __future__ import annotations

from pathlib import Path


def test_broker_rejects_non_runnable_agent_runs_before_capabilities() -> None:
    source = (
        Path(__file__).parents[2]
        / "app"
        / "agent_runtime"
        / "broker_api.py"
    ).read_text(encoding="utf-8")
    assert 'snapshot.status not in {"starting", "running", "waiting_for_approval"}' in source
    assert 'snapshot.desired_state != "running"' in source
