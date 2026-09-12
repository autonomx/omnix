from types import SimpleNamespace

from app.agent_runtime.coding_quality_repository import PostgresCodingQualityRepository


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, existing=None):
        self.existing = existing
        self.insert_args = None

    def execute(self, sql, args):
        if (
            "SELECT stage, attempt, task_revision_id, workspace_state_id" in sql
            and "FROM omnix_agent_coding_quality_state" in sql
        ):
            return _Cursor(self.existing)
        if "INSERT INTO omnix_agent_coding_quality_state" in sql:
            self.insert_args = args
            self.existing = (
                args[2],
                args[3],
                args[4],
                args[5],
                "stage-started",
                "updated",
            )
            return _Cursor(self.existing)
        raise AssertionError(f"unexpected SQL: {sql}")


def _repository(existing=None):
    connection = _Connection(existing)
    repository = PostgresCodingQualityRepository(
        connection,
        SimpleNamespace(workspace_id="workspace-1"),
    )
    return repository, connection


def test_initial_implementing_seed_starts_at_inspect():
    repository, connection = _repository()

    state = repository.set_stage(
        "run-1",
        stage="implementing",
        attempt=1,
        task_revision_id="revision-1",
    )

    assert state["stage"] == "inspect"
    assert connection.insert_args[2] == "inspect"


def test_same_revision_workspace_mutation_can_enter_implementing():
    repository, connection = _repository(
        ("planning", 1, "revision-1", None, "stage-started", "updated")
    )

    state = repository.set_stage(
        "run-1",
        stage="implementing",
        attempt=1,
        task_revision_id="revision-1",
    )

    assert state["stage"] == "implementing"
    assert connection.insert_args[2] == "implementing"


def test_new_task_revision_restarts_at_inspect_instead_of_implementing():
    repository, connection = _repository(
        ("implementing", 1, "revision-1", None, "stage-started", "updated")
    )

    state = repository.set_stage(
        "run-1",
        stage="implementing",
        attempt=1,
        task_revision_id="revision-2",
    )

    assert state["stage"] == "inspect"
    assert state["task_revision_id"] == "revision-2"
    assert connection.insert_args[2] == "inspect"


def test_explicit_planning_stage_is_preserved():
    repository, connection = _repository(
        ("inspect", 1, "revision-1", None, "stage-started", "updated")
    )

    state = repository.set_stage(
        "run-1",
        stage="planning",
        attempt=1,
        task_revision_id="revision-1",
    )

    assert state["stage"] == "planning"
    assert connection.insert_args[2] == "planning"
