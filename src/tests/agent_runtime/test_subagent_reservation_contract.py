from __future__ import annotations

from pathlib import Path

RUNTIME = Path(__file__).parents[2] / "app" / "agent_runtime"


def _method(source: str, name: str) -> str:
    return source.split(f"def {name}", 1)[1].split("\n    def ", 1)[0]


def test_child_start_locks_parent_checks_grant_then_persists_child_before_grant() -> None:
    core = (RUNTIME / "service_core.py").read_text(encoding="utf-8")
    service = (RUNTIME / "service.py").read_text(encoding="utf-8")
    create_block = _method(core, "_create_child_start")

    ordered = (
        "FOR UPDATE",
        "self._reserve_child_start(",
        "repository.create_run(child_spec)",
        "self._record_child_grant(",
        "work.commit()",
    )
    positions = [create_block.index(marker) for marker in ordered]
    assert positions == sorted(positions)

    reserve = _method(service, "_reserve_child_start")
    record = _method(service, "_record_child_grant")
    # The grant references the child row by foreign key, so the check runs
    # under the parent lock and the insert waits until the child exists.
    assert "grants.assert_can_grant(" in reserve
    assert "grants.add_grant(" not in reserve
    assert "grants.add_grant(" in record
    assert "reserve_child_budget(" not in reserve


def test_durable_child_submission_defers_workspace_work_until_after_the_parent_lock() -> None:
    core = (RUNTIME / "service_core.py").read_text(encoding="utf-8")
    submit = _method(core, "submit_child_start")

    assert submit.index("self._create_child_start(") < submit.index("enqueue_agent_job(")
    assert "_prepare_workspace(" not in submit
