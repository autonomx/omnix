from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.contracts import TaskRevision
from app.agent_runtime.task_revision_quality import persist_task_revision_contract


class _Result:
    def __init__(self, row=None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, latest_revision_id: str) -> None:
        self.latest_revision_id = latest_revision_id
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params):
        normalized = " ".join(str(sql).split())
        self.calls.append((normalized, tuple(params)))
        if normalized.startswith("SELECT revision_id FROM omnix_agent_task_revisions"):
            return _Result((self.latest_revision_id,))
        return _Result()


def _revision(revision_id: str) -> TaskRevision:
    return TaskRevision(
        revision_id=revision_id,
        run_id="run-1",
        sequence=2,
        user_instruction="new objective",
        effective_objective="new objective",
    )


def test_persisting_latest_revision_retires_pending_superseded_quality_resumes() -> None:
    connection = _Connection("revision-2")

    persist_task_revision_contract(
        connection,
        SimpleNamespace(workspace_id="workspace-1"),
        _revision("revision-2"),
    )

    retire_calls = [
        (sql, params)
        for sql, params in connection.calls
        if "UPDATE omnix_agent_run_commands" in sql
    ]
    assert len(retire_calls) == 1
    sql, params = retire_calls[0]
    assert "status = 'pending'" in sql
    assert "command_type = 'resume'" in sql
    assert "payload ? 'quality_stage'" in sql
    assert "task_revision_id" in sql
    assert params == ("workspace-1", "run-1", "revision-2")


def test_persisting_latest_revision_stales_superseded_planning_authority() -> None:
    connection = _Connection("revision-2")

    persist_task_revision_contract(
        connection,
        SimpleNamespace(workspace_id="workspace-1"),
        _revision("revision-2"),
    )

    planning_calls = [
        (sql, params)
        for sql, params in connection.calls
        if "UPDATE omnix_agent_planning_state" in sql
    ]
    assert len(planning_calls) == 1
    sql, params = planning_calls[0]
    assert "SET status = 'stale'" in sql
    assert "task_revision_id IS DISTINCT FROM" in sql
    assert params == ("workspace-1", "run-1", "revision-2")


def test_persisting_non_latest_revision_does_not_retire_or_stale_authority() -> None:
    connection = _Connection("revision-3")

    persist_task_revision_contract(
        connection,
        SimpleNamespace(workspace_id="workspace-1"),
        _revision("revision-2"),
    )

    assert not any(
        "UPDATE omnix_agent_run_commands" in sql
        for sql, _params in connection.calls
    )
    assert not any(
        "UPDATE omnix_agent_planning_state" in sql
        for sql, _params in connection.calls
    )
