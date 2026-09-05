from __future__ import annotations

from pathlib import Path


def test_child_start_locks_parent_before_budget_reservation() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "service.py").read_text(encoding="utf-8")
    child_block = source.split("def start_child", 1)[1].split("def _persist_starting_run", 1)[0]
    reservation_call = "reserve_child_budget("
    assert "FOR UPDATE" in child_block
    assert reservation_call in child_block
    assert child_block.index("FOR UPDATE") < child_block.index(reservation_call)
    assert child_block.index(reservation_call) < child_block.index("_persist_starting_run")
