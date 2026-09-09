from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime import service as service_module
from app.agent_runtime import service_core as core_module
from app.agent_runtime.acceptance import AcceptanceResult
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    EvidenceSet,
    ModelRef,
    TaskRevision,
    WorkspaceSpec,
    WorkspaceState,
)
from app.agent_runtime.planning_acceptance import PlanningAcceptanceAssessment
from app.agent_runtime.service import AgentRunService


class _Work:
    connection = object()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _spec(run_id: str = "run-1") -> AgentRunSpec:
    return AgentRunSpec(
        run_id=run_id,
        task="Fix the dropdown",
        objective="Fix the dropdown",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        expected_artifacts=["diff"],
        quality_policy="strict",
        workspace=WorkspaceSpec(root="/tmp/work", repository="/tmp/work"),
    )


def test_durable_resume_rehydrates_missing_runtime_before_consumption(monkeypatch) -> None:
    spec = _spec("resume-run")
    state = {"snapshot": AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")}
    runtime_state = {"active": None}
    sent: list[AgentRunCommand] = []

    class Repository:
        def __init__(self, _connection, _context):
            pass

        def get_run(self, _run_id):
            return state["snapshot"]

        def update_state(self, _run_id, **kwargs):
            state["snapshot"] = state["snapshot"].model_copy(update=kwargs)
            return state["snapshot"]

    def start(_spec):
        runtime_state["active"] = AgentRunSnapshot(
            run_id=spec.run_id, spec=spec, status="running", desired_state="running"
        )
        return runtime_state["active"]

    def command(command):
        sent.append(command)
        return runtime_state["active"]

    runtime = SimpleNamespace(
        get_status=lambda _run_id: runtime_state["active"],
        start=MagicMock(side_effect=start),
        command=MagicMock(side_effect=command),
    )
    service = object.__new__(core_module.AgentRunService)
    service.database = object()
    service.context = object()
    service.runtime = runtime

    monkeypatch.setattr(core_module, "unit_of_work", lambda _database: _Work())
    monkeypatch.setattr(core_module, "PostgresAgentRunRepository", Repository)

    resume = AgentRunCommand(
        run_id=spec.run_id,
        command_type="resume",
        payload={"message": "Continue quality validation", "quality_stage": "validating"},
    )
    result = service._apply_claimed_command(resume)

    runtime.start.assert_called_once_with(spec)
    runtime.command.assert_called_once()
    assert sent[0].payload["runtime_rehydrated"] is True
    assert result.status == "running"
    assert result.desired_state == "running"


def test_stall_supervisor_recovers_stranded_resume_requested(monkeypatch) -> None:
    spec = _spec("stranded-resume")
    state = {
        "snapshot": AgentRunSnapshot(
            run_id=spec.run_id, spec=spec, status="resume_requested", desired_state="running"
        )
    }
    progress = AgentEvent(
        run_id=spec.run_id,
        event_type="run.status",
        payload={"status": "resume_requested"},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    events: list[AgentEvent] = []

    class Repository:
        def __init__(self, _connection, _context):
            pass

        def get_run(self, _run_id):
            return state["snapshot"]

        def latest_progress_event(self, _run_id):
            return progress

        def count_events(self, _run_id, _event_type):
            return 0

        def list_events(self, _run_id, *, after_sequence=0, limit=5000):
            del after_sequence, limit
            return []

        def append_event(self, event):
            events.append(event)

        def update_state(self, _run_id, **kwargs):
            state["snapshot"] = state["snapshot"].model_copy(update=kwargs)
            return state["snapshot"]

    runtime = SimpleNamespace(
        get_status=MagicMock(return_value=None),
        close_run=MagicMock(),
        start=MagicMock(),
        command=MagicMock(),
    )
    service = object.__new__(core_module.AgentRunService)
    service.database = object()
    service.context = object()
    service.worker_id = "worker-1"
    service.runtime = runtime
    import threading
    service._lock = threading.RLock()
    service._cancel_descendants = MagicMock()

    monkeypatch.setenv("OMNIX_AGENT_PROGRESS_IDLE_TIMEOUT_SECONDS", "60")
    monkeypatch.setattr(core_module, "unit_of_work", lambda _database: _Work())
    monkeypatch.setattr(core_module, "PostgresAgentRunRepository", Repository)

    service._supervise_stalled_run(spec.run_id)

    runtime.start.assert_called_once_with(spec)
    runtime.command.assert_called_once()
    assert state["snapshot"].status == "running"
    assert any(event.event_type == "run.recovery_requested" for event in events)


def test_post_review_workspace_drift_refreshes_same_quality_attempt(monkeypatch) -> None:
    spec = _spec("drift-run")
    current = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    revision = TaskRevision(
        revision_id="revision-1",
        run_id=spec.run_id,
        sequence=1,
        user_instruction="Fix the dropdown",
        effective_objective="Fix the dropdown",
    )
    current_state = WorkspaceState(
        state_id="new-state",
        run_id=spec.run_id,
        task_revision_id=revision.revision_id,
        base_commit_sha="b" * 40,
        tracked_diff_sha256="c" * 64,
        untracked_file_manifest_sha256="d" * 64,
    )

    class Repository:
        connection = object()

        def append_event(self, _event):
            pass

        def list_events(self, _run_id, *, after_sequence=0, limit=5000):
            del after_sequence, limit
            return []

        def list_artifacts(self, _run_id):
            return []

        def list_evidence_receipts(self, _run_id):
            return []

        def list_children(self, _run_id):
            return []

        def get_run(self, _run_id):
            return current

    class Quality:
        def __init__(self, _connection, _context):
            pass

        def get_stage(self, _run_id):
            return {
                "stage": "acceptance",
                "attempt": 1,
                "task_revision_id": revision.revision_id,
                "workspace_state_id": "reviewed-state",
            }

        def add_workspace_state(self, _state):
            pass

        def list_validation_results(self, *_args, **_kwargs):
            return []

        def list_review_results(self, *_args, **_kwargs):
            return []

        def list_self_review_results(self, *_args, **_kwargs):
            return []

    service = object.__new__(AgentRunService)
    service.context = object()
    service.worker_id = "worker-1"
    service._capture_diff = MagicMock()
    service._current_revision = lambda _repository, _run_id: revision
    service._request_quality_workspace_refresh = MagicMock(return_value=None)
    service._request_quality_repair = MagicMock(return_value=None)
    service._quality_fail = MagicMock(return_value=None)

    monkeypatch.setattr(service_module, "PostgresCodingQualityRepository", Quality)
    monkeypatch.setattr(service_module, "capture_workspace_state", lambda *_args, **_kwargs: current_state)
    monkeypatch.setattr(
        service_module,
        "evaluate_acceptance",
        lambda *_args, **_kwargs: AcceptanceResult(passed=True),
    )
    monkeypatch.setattr(
        service_module,
        "evaluate_evidence_set",
        lambda *_args, **_kwargs: EvidenceSet(run_id=spec.run_id),
    )
    monkeypatch.setattr(
        service_module,
        "quality_failure_reasons",
        lambda *_args, **_kwargs: [
            "quality_missing_validation:final-state-tests",
            "quality_self_review_stale_or_missing",
            "quality_independent_review_missing_or_not_approved",
        ],
    )
    monkeypatch.setattr(
        service_module,
        "evaluate_planning_acceptance",
        lambda *_args, **_kwargs: PlanningAcceptanceAssessment(
            mode="shadow",
            plan_revision_id="plan-1",
            failures=("planning_base_commit_changed",),
        ),
    )

    service._finalize_acceptance(Repository(), current)

    service._request_quality_workspace_refresh.assert_called_once()
    kwargs = service._request_quality_workspace_refresh.call_args.kwargs
    assert kwargs["current_workspace_state_id"] == "new-state"
    assert kwargs["prior_workspace_state_id"] == "reviewed-state"
    service._request_quality_repair.assert_not_called()
    service._quality_fail.assert_not_called()


def test_enforced_post_review_workspace_drift_fails_integrity_not_quality_repair(monkeypatch) -> None:
    spec = _spec("enforced-drift")
    current = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    revision = TaskRevision(
        revision_id="revision-1",
        run_id=spec.run_id,
        sequence=1,
        user_instruction="Fix the dropdown",
        effective_objective="Fix the dropdown",
    )
    current_state = WorkspaceState(
        state_id="new-state",
        run_id=spec.run_id,
        task_revision_id=revision.revision_id,
        base_commit_sha="b" * 40,
        tracked_diff_sha256="c" * 64,
        untracked_file_manifest_sha256="d" * 64,
    )

    class Repository:
        connection = object()
        def append_event(self, _event): pass
        def list_events(self, _run_id, *, after_sequence=0, limit=5000): return []
        def list_artifacts(self, _run_id): return []
        def list_evidence_receipts(self, _run_id): return []
        def list_children(self, _run_id): return []
        def get_run(self, _run_id): return current

    class Quality:
        def __init__(self, _connection, _context): pass
        def get_stage(self, _run_id): return {"stage": "acceptance", "attempt": 1, "workspace_state_id": "reviewed-state"}
        def add_workspace_state(self, _state): pass
        def list_validation_results(self, *_args, **_kwargs): return []
        def list_review_results(self, *_args, **_kwargs): return []
        def list_self_review_results(self, *_args, **_kwargs): return []

    service = object.__new__(AgentRunService)
    service.context = object()
    service.worker_id = "worker-1"
    service._capture_diff = MagicMock()
    service._current_revision = lambda _repository, _run_id: revision
    service._request_quality_workspace_refresh = MagicMock(return_value=None)
    service._request_quality_repair = MagicMock(return_value=None)
    service._quality_fail = MagicMock(return_value=None)

    monkeypatch.setattr(service_module, "PostgresCodingQualityRepository", Quality)
    monkeypatch.setattr(service_module, "capture_workspace_state", lambda *_args, **_kwargs: current_state)
    monkeypatch.setattr(service_module, "evaluate_acceptance", lambda *_args, **_kwargs: AcceptanceResult(passed=True))
    monkeypatch.setattr(service_module, "evaluate_evidence_set", lambda *_args, **_kwargs: EvidenceSet(run_id=spec.run_id))
    monkeypatch.setattr(service_module, "quality_failure_reasons", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        service_module,
        "evaluate_planning_acceptance",
        lambda *_args, **_kwargs: PlanningAcceptanceAssessment(
            mode="enforce",
            plan_revision_id="plan-1",
            failures=("planning_base_commit_changed",),
            hard_gate_required=True,
        ),
    )

    service._finalize_acceptance(Repository(), current)

    service._quality_fail.assert_called_once()
    assert "review_integrity_failed:workspace_changed_after_review" in service._quality_fail.call_args.args[2]
    service._request_quality_workspace_refresh.assert_not_called()
    service._request_quality_repair.assert_not_called()
