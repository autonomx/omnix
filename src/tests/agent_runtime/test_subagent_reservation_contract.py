from __future__ import annotations

from pathlib import Path


def test_child_start_locks_parent_before_durable_grant_and_persists_grant_before_commit() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "service.py").read_text(encoding="utf-8")
    child_block = source.split("def start_child", 1)[1].split("def _persist_starting_run", 1)[0]

    lock = "FOR UPDATE"
    grant_check = "grants.assert_can_grant("
    persist_child = "self._persist_starting_run(repository, issued)"
    persist_grant = "grants.add_grant("
    commit = "work.commit()"

    for marker in (lock, grant_check, persist_child, persist_grant, commit):
        assert marker in child_block

    assert child_block.index(lock) < child_block.index(grant_check)
    assert child_block.index(grant_check) < child_block.index(persist_child)
    assert child_block.index(persist_child) < child_block.index(persist_grant)
    assert child_block.index(persist_grant) < child_block.index(commit)
    assert "reserve_child_budget(" not in child_block
