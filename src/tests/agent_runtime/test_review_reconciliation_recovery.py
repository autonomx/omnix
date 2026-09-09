from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime import quality_recovery as recovery_module
from app.agent_runtime import review_orchestration as orchestration_module
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
    ReviewAttempt,
    ReviewResult,
    ReviewSnapshot,
    TaskRevision,
    WorkspaceState,
)
from app.agent_runtime.quality_recovery import _promote_protocol_complete_reviewers
from app.agent_runtime.review_orchestration import reconcile_review_progress_in_repository


class _Work:
    connection = object()

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _parent() -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="parent-1",
        task="Fix the dropdown",
        objective="Fix the dropdown",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        expected_artifacts=["diff"],
        quality_policy="strict",
    )
    return AgentRunSnapshot(
        run_id=spec.run_id,
        spec=spec,
        status="waiting_for_children",
    )


def _reviewer(*, status: str = "running") -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="reviewer-1",
        parent_run_id="parent-1",
        task=(
            "REVIEW_SNAPSHOT_ID=abc123\n"
            "REVIEW_SLOT=0\n"
            "REVIEW_RUNTIME_ATTEMPT=1\n"
            "Review immutable snapshot"
        ),
        objective="Review immutable snapshot",
        profile="coding-reviewer",
        model=ModelRef(provider_id="test", model_id="model"),
        quality_policy="off",
    )
    return AgentRunSnapshot(run_id=spec.run_id, spec=spec, status=status)


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1",
        run_id="parent-1",
        sequence=1,
        user_instruction="Fix the dropdown",
        effective_objective="Fix the dropdown",
    )


def _state() -> WorkspaceState:
    return WorkspaceState(
        state_id="state-1",
        run_id="parent-1",
        task_revision_id="revision-1",
        base_commit_sha="a" * 40,
        tracked_diff_sha256="b" * 64,
        untracked_file_manifest_sha256="c" * 64,
        modified_paths=["src/ui.tsx"],
    )


def _snapshot() -> ReviewSnapshot:
    return ReviewSnapshot(
        snapshot_id="abc123",
        run_id="parent-1",
        task_revision_id="revision-1",
        workspace_state_id="state-1",
        base_commit_sha="a" * 40,
        patch_checksum="d" * 64,
        workspace_root="/tmp/review",
    )


def test_protocol_valid_final_message_terminalizes_reviewer_without_waiting_for_settled(
    monkeypatch,
) -> None:
    parent = _parent()
    child_state = {"snapshot": _reviewer(status="running")}
    revision = _revision()
    snapshot = _snapshot()
    closed: list[str] = []
    final_payload = (
        '{"verdict":"approve","requirements":[],"findings":[],'
        '"missing_tests":[],"residual_risks":[]}'
    )

    class Repository:
        def __init__(self, _connection, _context):
            pass

        def get_run(self, run_id):
            if run_id == parent.run_id:
                return parent
            if run_id == child_state["snapshot"].run_id:
                return child_state["snapshot"]
            return None

        def list_children(self, _run_id):
            return [child_state["snapshot"]]

        def list_events(self, _run_id, *, after_sequence=0, limit=5000):
            del after_sequence, limit
            return [
                AgentEvent(
                    run_id="reviewer-1",
                    event_type="model.message",
                    payload={"phase": "message_end", "text": final_payload},
                )
            ]

        def update_state(self, run_id, **kwargs):
            assert run_id == "reviewer-1"
            child_state["snapshot"] = child_state["snapshot"].model_copy(update=kwargs)
            return child_state["snapshot"]

    class Quality:
        def __init__(self, _connection, _context):
            pass

        def get_stage(self, _run_id):
            return {"stage": "reviewing", "workspace_state_id": "state-1"}

        def latest_review_snapshot(self, *_args, **_kwargs):
            return snapshot

    service = SimpleNamespace(
        database=object(),
        context=object(),
        _current_revision=lambda _repository, _run_id: revision,
        _close_terminal_runtime=lambda run_id: closed.append(run_id),
    )

    monkeypatch.setattr(recovery_module, "unit_of_work", lambda _database: _Work())
    monkeypatch.setattr(recovery_module, "PostgresAgentRunRepository", Repository)
    monkeypatch.setattr(recovery_module, "PostgresCodingQualityRepository", Quality)

    promoted = _promote_protocol_complete_reviewers(service, parent.run_id)

    assert promoted == ["reviewer-1"]
    assert child_state["snapshot"].status == "completed"
    assert closed == ["reviewer-1"]


def test_approved_reviewer_result_advances_parent_through_acceptance(monkeypatch) -> None:
    parent_state = {"snapshot": _parent()}
    child = _reviewer(status="completed")
    revision = _revision()
    state = _state()
    snapshot = _snapshot()
    attempt = ReviewAttempt(
        review_attempt_id="attempt-1",
        run_id="parent-1",
        reviewer_run_id="reviewer-1",
        review_snapshot_id="abc123",
        task_revision_id="revision-1",
        workspace_state_id="state-1",
        reviewer_slot=0,
        runtime_attempt=1,
        protocol_version="review-v2",
        model_provider_id="test",
        model_id="model",
        status="completed",
    )
    result = ReviewResult(
        review_result_id="result-1",
        run_id="parent-1",
        reviewer_run_id="reviewer-1",
        review_snapshot_id="abc123",
        task_revision_id="revision-1",
        workspace_state_id="state-1",
        verdict="approve",
    )
    stage = {"stage": "reviewing", "attempt": 1, "workspace_state_id": "state-1"}
    finalized: list[str] = []

    class Repository:
        connection = object()

        def get_run(self, run_id):
            if run_id == "parent-1":
                return parent_state["snapshot"]
            if run_id == "reviewer-1":
                return child
            return None

        def list_children(self, _run_id):
            return [child]

        def update_state(self, run_id, **kwargs):
            assert run_id == "parent-1"
            parent_state["snapshot"] = parent_state["snapshot"].model_copy(update=kwargs)
            return parent_state["snapshot"]

    class Quality:
        def __init__(self, _connection, _context):
            pass

        def get_stage(self, _run_id):
            return dict(stage)

        def get_workspace_state(self, _run_id, _state_id):
            return state

        def latest_review_snapshot(self, *_args, **_kwargs):
            return snapshot

        def list_review_results(self, *_args, **_kwargs):
            return [result]

        def list_review_attempts(self, *_args, **_kwargs):
            return [attempt]

    service = SimpleNamespace(
        context=object(),
        worker_id="worker-1",
        _quality_enabled=lambda _spec: True,
        _current_revision=lambda _repository, _run_id: revision,
        _quality_fail=MagicMock(),
        _request_quality_repair=MagicMock(),
    )

    def set_stage(_repository, **kwargs):
        stage.update({
            "stage": kwargs["stage"],
            "attempt": kwargs["attempt"],
            "workspace_state_id": kwargs.get("workspace_state_id"),
        })

    def finalize(_repository, current):
        finalized.append(current.run_id)
        parent_state["snapshot"] = parent_state["snapshot"].model_copy(
            update={"status": "completed"}
        )

    service._set_quality_stage = set_stage
    service._finalize_acceptance = finalize

    monkeypatch.setattr(
        orchestration_module,
        "PostgresCodingQualityRepository",
        Quality,
    )
    monkeypatch.setattr(
        orchestration_module,
        "consume_terminal_reviewer_in_repository",
        lambda *_args, **_kwargs: result,
    )

    action = reconcile_review_progress_in_repository(service, Repository(), "parent-1")

    assert action is None
    assert finalized == ["parent-1"]
    assert stage["stage"] == "acceptance"
    assert parent_state["snapshot"].status == "completed"
    service._request_quality_repair.assert_not_called()
    service._quality_fail.assert_not_called()
