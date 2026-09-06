from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
    TaskRequirement,
    TaskRevision,
)
from app.agent_runtime.service import (
    AgentRunService,
    _implementation_candidate_failures,
    _implementation_candidate_retry_count,
    _implementation_candidate_retry_limit,
    _pre_review_gate,
    _self_review_payload_is_protocol_valid,
    _self_review_protocol_retry_count,
    _self_review_protocol_retry_limit,
    _terminal_message_settles_quality_stage,
)


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1",
        run_id="run-1",
        sequence=1,
        user_instruction="fix it",
        effective_objective="fix it",
        requirements=[
            TaskRequirement(
                id="requirement-1",
                description="requested behavior is correct",
                required=True,
            )
        ],
    )


def _snapshot() -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="run-1",
        task="fix it",
        objective="fix it",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        expected_artifacts=["diff"],
        quality_policy="strict",
    )
    return AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")


def _valid_payload() -> str:
    return (
        '{"verdict":"approve","requirements":['
        '{"requirement_id":"requirement-1","status":"satisfied","evidence":"checked"}'
        '],"findings":[],"missing_tests":[],"residual_risks":[]}'
    )


def test_self_review_protocol_validation_is_distinct_from_quality_verdict() -> None:
    revision = _revision()
    assert _self_review_payload_is_protocol_valid(_valid_payload(), revision)
    assert not _self_review_payload_is_protocol_valid("", revision)
    assert not _self_review_payload_is_protocol_valid('{"verdict":"approve"}', revision)
    assert not _self_review_payload_is_protocol_valid(
        '{"verdict":"approve","requirements":[],"findings":[],"missing_tests":[],"residual_risks":[]}',
        revision,
    )


def test_malformed_self_review_text_waits_for_pi_settle_boundary() -> None:
    malformed = AgentEvent(
        run_id="run-1",
        event_type="model.message",
        payload={"phase": "message_end", "text": "I could not format the verdict."},
    )
    structured = AgentEvent(
        run_id="run-1",
        event_type="model.message",
        payload={"phase": "message_end", "text": _valid_payload()},
    )
    assert not _terminal_message_settles_quality_stage(malformed, "self_review")
    assert _terminal_message_settles_quality_stage(structured, "self_review")


def test_protocol_retry_count_is_bound_to_attempt_revision_and_workspace_state() -> None:
    events = [
        AgentEvent(
            run_id="run-1",
            sequence=1,
            event_type="quality.self_review_protocol_retry_requested",
            payload={
                "quality_attempt": 2,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-1",
            },
        ),
        AgentEvent(
            run_id="run-1",
            sequence=2,
            event_type="quality.self_review_protocol_retry_requested",
            payload={
                "quality_attempt": 1,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-1",
            },
        ),
        AgentEvent(
            run_id="run-1",
            sequence=3,
            event_type="quality.self_review_protocol_retry_requested",
            payload={
                "quality_attempt": 2,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-2",
            },
        ),
    ]

    class Repository:
        def list_events(self, _run_id, *, after_sequence, limit):
            assert limit == 2
            if after_sequence == 0:
                return events[:2]
            if after_sequence == 2:
                return events[2:]
            return []

    assert _self_review_protocol_retry_count(
        Repository(),
        run_id="run-1",
        attempt=2,
        task_revision_id="revision-1",
        workspace_state_id="state-1",
        page_size=2,
    ) == 1


def test_protocol_retry_limit_is_bounded_and_has_safe_default(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_SELF_REVIEW_PROTOCOL_RETRIES", raising=False)
    assert _self_review_protocol_retry_limit() == 2
    monkeypatch.setenv("OMNIX_AGENT_SELF_REVIEW_PROTOCOL_RETRIES", "99")
    assert _self_review_protocol_retry_limit() == 5
    monkeypatch.setenv("OMNIX_AGENT_SELF_REVIEW_PROTOCOL_RETRIES", "invalid")
    assert _self_review_protocol_retry_limit() == 2


def test_quality_resume_is_persisted_to_command_outbox_before_dispatch() -> None:
    stored = []

    class Repository:
        def enqueue_command_with_status(self, command):
            stored.append(command)
            return command, "pending"

    service = object.__new__(AgentRunService)
    action = service._queue_quality_resume(
        Repository(),
        run_id="run-1",
        prompt="return the verdict",
        idempotency_key="quality-self-review:run-1:revision-1:1",
        quality_stage="self_review",
        quality_attempt=1,
        task_revision_id="revision-1",
        workspace_state_id="state-1",
    )

    assert len(stored) == 1
    assert stored[0].command_type == "resume"
    assert stored[0].payload["quality_stage"] == "self_review"
    assert action == ("dispatch_command", stored[0])


def test_consumed_quality_resume_is_not_dispatched_twice() -> None:
    command_holder = []

    class Repository:
        def enqueue_command_with_status(self, command):
            command_holder.append(command)
            return command, "consumed"

    service = object.__new__(AgentRunService)
    assert service._queue_quality_resume(
        Repository(),
        run_id="run-1",
        prompt="validate",
        idempotency_key="quality-validation:run-1:state-1:1",
        quality_stage="validating",
        quality_attempt=1,
        task_revision_id="revision-1",
        workspace_state_id="state-1",
    ) is None


def test_quality_dispatch_uses_normal_durable_command_path() -> None:
    snapshot = _snapshot()
    service = object.__new__(AgentRunService)
    service.command = MagicMock(return_value=snapshot)
    service.runtime = SimpleNamespace(command=MagicMock())
    command = SimpleNamespace(run_id="run-1")

    service._execute_quality_action(("dispatch_command", command))

    service.command.assert_called_once_with(command)
    service.runtime.command.assert_not_called()


def test_missing_self_review_retries_protocol_without_consuming_quality_attempt(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SELF_REVIEW_PROTOCOL_RETRIES", "2")
    snapshot = _snapshot()
    revision = _revision()
    events = []
    commands = []
    updates = []

    class Repository:
        def list_events(self, _run_id, *, after_sequence, limit):
            del after_sequence, limit
            return list(events)

        def append_event(self, event):
            events.append(event.model_copy(update={"sequence": len(events) + 1}))

        def enqueue_command_with_status(self, command):
            commands.append(command)
            return command, "pending"

        def get_run(self, _run_id):
            return snapshot

        def update_state(self, _run_id, **kwargs):
            updates.append(kwargs)
            return snapshot.model_copy(update=kwargs)

    quality = SimpleNamespace(list_validation_results=lambda *_args, **_kwargs: [])
    service = object.__new__(AgentRunService)
    service._set_quality_stage = MagicMock()

    action = service._request_self_review_protocol_retry(
        Repository(),
        snapshot,
        revision,
        quality,
        attempt=2,
        workspace_state_id="state-1",
        response_text="",
    )

    assert action is not None and action[0] == "dispatch_command"
    assert commands and commands[0].payload["quality_attempt"] == 2
    assert not updates
    assert any(
        event.event_type == "quality.self_review_protocol_retry_requested"
        and event.payload["quality_attempt"] == 2
        and event.payload["protocol_retry"] == 1
        for event in events
    )
    assert not any(event.event_type == "quality.repair_requested" for event in events)
    service._set_quality_stage.assert_called_once()
    assert service._set_quality_stage.call_args.kwargs["attempt"] == 2


def test_protocol_exhaustion_fails_with_transport_specific_reason(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SELF_REVIEW_PROTOCOL_RETRIES", "2")
    snapshot = _snapshot()
    revision = _revision()
    updates = []
    events = [
        AgentEvent(
            run_id="run-1",
            sequence=index + 1,
            event_type="quality.self_review_protocol_retry_requested",
            payload={
                "quality_attempt": 2,
                "protocol_retry": index + 1,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-1",
            },
        )
        for index in range(2)
    ]

    class Repository:
        def list_events(self, _run_id, *, after_sequence, limit):
            del after_sequence, limit
            return list(events)

        def append_event(self, event):
            events.append(event.model_copy(update={"sequence": len(events) + 1}))

        def get_run(self, _run_id):
            return snapshot

        def update_state(self, _run_id, **kwargs):
            updates.append(kwargs)
            return snapshot.model_copy(update=kwargs)

    service = object.__new__(AgentRunService)
    service._set_quality_stage = MagicMock()
    quality = SimpleNamespace(list_validation_results=lambda *_args, **_kwargs: [])

    action = service._request_self_review_protocol_retry(
        Repository(),
        snapshot,
        revision,
        quality,
        attempt=2,
        workspace_state_id="state-1",
        response_text="still no JSON",
    )

    assert action is None
    assert updates[-1]["status"] == "failed"
    assert updates[-1]["desired_state"] == "cancelled"
    assert updates[-1]["last_error"] == "quality_failed:quality_self_review_protocol_exhausted"
    assert any(event.event_type == "quality.self_review_protocol_exhausted" for event in events)
    assert not any(event.event_type == "quality.repair_requested" for event in events)


def test_pre_review_gate_validates_before_self_review_even_with_nonempty_diff() -> None:
    revision = _revision().model_copy(
        update={
            "validation_plan": [
                {
                    "id": "final-state-tests",
                    "kind": "test",
                    "description": "focused tests",
                    "covers": ["requirement-1"],
                    "required": True,
                }
            ]
        }
    )
    diff = SimpleNamespace(
        metadata={
            "byte_size": 42,
            "modified_paths": ["src/app.tsx"],
            "baseline_conflicts": [],
        }
    )
    gate, details = _pre_review_gate(
        revision,
        [],
        workspace_state_id="state-1",
        diff_artifact=diff,
    )
    assert gate == "validating"
    assert [item.id for item in details] == ["final-state-tests"]


def test_empty_candidate_cannot_enter_self_review_without_behavioral_proof() -> None:
    empty_diff = SimpleNamespace(
        metadata={
            "byte_size": 0,
            "modified_paths": [],
            "baseline_conflicts": [],
        }
    )
    assert _implementation_candidate_failures(empty_diff, []) == [
        "empty_run_owned_diff_without_already_satisfied_proof"
    ]
    browser_proof = SimpleNamespace(validation_id="browser-validation", success=True)
    assert _implementation_candidate_failures(empty_diff, [browser_proof]) == []


def test_implementation_candidate_retry_count_is_attempt_and_revision_bound() -> None:
    events = [
        AgentEvent(
            run_id="run-1",
            sequence=1,
            event_type="quality.implementation_continuation_requested",
            payload={"quality_attempt": 2, "task_revision_id": "revision-1"},
        ),
        AgentEvent(
            run_id="run-1",
            sequence=2,
            event_type="quality.implementation_continuation_requested",
            payload={"quality_attempt": 1, "task_revision_id": "revision-1"},
        ),
        AgentEvent(
            run_id="run-1",
            sequence=3,
            event_type="quality.implementation_continuation_requested",
            payload={"quality_attempt": 2, "task_revision_id": "revision-2"},
        ),
    ]

    class Repository:
        def list_events(self, _run_id, *, after_sequence, limit):
            assert limit == 2
            if after_sequence == 0:
                return events[:2]
            if after_sequence == 2:
                return events[2:]
            return []

    assert _implementation_candidate_retry_count(
        Repository(),
        run_id="run-1",
        attempt=2,
        task_revision_id="revision-1",
        page_size=2,
    ) == 1


def test_implementation_candidate_retry_limit_is_bounded(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_IMPLEMENTATION_SETTLE_RETRIES", raising=False)
    assert _implementation_candidate_retry_limit() == 2
    monkeypatch.setenv("OMNIX_AGENT_IMPLEMENTATION_SETTLE_RETRIES", "99")
    assert _implementation_candidate_retry_limit() == 5
    monkeypatch.setenv("OMNIX_AGENT_IMPLEMENTATION_SETTLE_RETRIES", "invalid")
    assert _implementation_candidate_retry_limit() == 2
