"""A run ends through one place (deep-modules wave 2).

That a lease-bound repository fences each ending with its lease is checked on
PostgreSQL in ``test_agent_runtime_repository_integration``.
"""
from __future__ import annotations

from app.platform.agent_runtime.run_settlement import ERROR_LIMIT, cancel_run, complete_run, fail_run


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def update_state(self, run_id: str, **kwargs):
        self.calls.append((run_id, kwargs))
        return kwargs


def test_each_ending_sets_its_status_desired_state_and_error() -> None:
    repository = _Recorder()

    fail_run(repository, "r1", expected_revision=3, error="x" * (ERROR_LIMIT + 50), worker_id="w")
    complete_run(repository, "r2", expected_revision=4)
    cancel_run(repository, "r3", expected_revision=5, worker_id="w", lease_token="t")

    failed, completed, cancelled = (kwargs for _, kwargs in repository.calls)
    assert failed == {
        "expected_revision": 3, "status": "failed", "desired_state": "cancelled",
        "last_error": "x" * ERROR_LIMIT, "worker_id": "w",
    }
    assert completed == {"expected_revision": 4, "status": "completed", "last_error": None}
    assert cancelled == {
        "expected_revision": 5, "status": "cancelled", "desired_state": "cancelled",
        "worker_id": "w", "lease_token": "t",
    }


def test_a_stop_that_went_wrong_keeps_its_reason() -> None:
    repository = _Recorder()

    cancel_run(repository, "r1", expected_revision=1, error="command_failed:" + "y" * ERROR_LIMIT)

    assert repository.calls[0][1]["status"] == "cancelled"
    assert repository.calls[0][1]["last_error"] == ("command_failed:" + "y" * ERROR_LIMIT)[:ERROR_LIMIT]


def test_no_module_writes_a_terminal_status_by_hand() -> None:
    import ast
    from pathlib import Path

    import app.platform.agent_runtime as package

    terminal = {"completed", "failed", "cancelled"}
    offenders = []
    for path in sorted(Path(package.__file__).parent.rglob("*.py")):
        if path.name == "run_settlement.py":
            continue
        for call in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(call, ast.Call) and getattr(call.func, "attr", None) == "update_state"):
                continue
            for keyword in call.keywords:
                if keyword.arg == "status" and any(
                    isinstance(node, ast.Constant) and node.value in terminal for node in ast.walk(keyword.value)
                ):
                    offenders.append(f"{path.name}:{call.lineno}")
    assert offenders == [], "end a run with run_settlement.fail_run/complete_run/cancel_run: " + ", ".join(offenders)
