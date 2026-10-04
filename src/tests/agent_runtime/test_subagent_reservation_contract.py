from __future__ import annotations

import ast
from pathlib import Path

RUNTIME = Path(__file__).parents[2] / "app" / "agent_runtime"


def _implementation(name: str, module: str) -> str:
    """The source of ``name`` in ``module`` (its implementation, not a delegator)."""
    for path in (RUNTIME / module,):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                segment = ast.get_source_segment(source, node) or ""
                if "from . import" not in segment:
                    return segment
    raise AssertionError(f"no implementation of {name} in {module}")


def test_child_start_locks_parent_checks_grant_then_persists_child_before_grant() -> None:
    create_block = _implementation("_create_child_start", "run_lifecycle.py")

    ordered = (
        ".lock_run(parent_run_id)",
        "._reserve_child_start(",
        "repository.create_run(child_spec)",
        "._record_child_grant(",
        "work.commit()",
    )
    positions = [create_block.index(marker) for marker in ordered]
    assert positions == sorted(positions)

    reserve = _implementation("_reserve_child_start", "service.py")
    record = _implementation("_record_child_grant", "service.py")
    # The grant references the child row by foreign key, so the check runs
    # under the parent lock and the insert waits until the child exists.
    assert "grants.assert_can_grant(" in reserve
    assert "grants.add_grant(" not in reserve
    assert "grants.add_grant(" in record
    assert "reserve_child_budget(" not in reserve


def test_durable_child_submission_defers_workspace_work_until_after_the_parent_lock() -> None:
    submit = _implementation("submit_child_start", "run_lifecycle.py")

    assert submit.index("._create_child_start(") < submit.index("enqueue_agent_job(")
    assert "_prepare_workspace(" not in submit
