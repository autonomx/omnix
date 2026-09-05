from __future__ import annotations

from app.agent_runtime.pi_runtime import PiAgentRuntime


def test_pi_runtime_exposes_terminal_process_cleanup() -> None:
    runtime = PiAgentRuntime(pi_path="pi")
    assert runtime.active_run_ids() == set()
    runtime.close_run("missing")
