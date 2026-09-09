from __future__ import annotations

from app.agent_runtime.contracts import AgentEvent
from app.agent_runtime.service import (
    _self_review_response_from_repository,
    _terminal_message_settles_quality_stage,
)


def _structured_payload() -> str:
    return (
        '{"verdict":"approve","requirements":['
        '{"requirement_id":"requirement-1","status":"satisfied","evidence":"checked"}'
        '],"findings":[],"missing_tests":[],"residual_risks":[]}'
    )


class _Repository:
    def __init__(self, events: list[AgentEvent]) -> None:
        self.events = events

    def list_events(self, _run_id: str, *, after_sequence: int, limit: int):
        rows = [
            event
            for event in self.events
            if int(event.sequence or 0) > after_sequence
        ]
        return rows[:limit]


def test_structured_implementation_message_is_not_a_self_review_boundary() -> None:
    event = AgentEvent(
        run_id="run-1",
        event_type="model.message",
        payload={"phase": "message_end", "text": _structured_payload()},
    )

    assert not _terminal_message_settles_quality_stage(event, "implementing")
    assert not _terminal_message_settles_quality_stage(event, "repairing")
    assert not _terminal_message_settles_quality_stage(event, "validating")
    assert _terminal_message_settles_quality_stage(event, "self_review")


def test_pre_marker_structured_json_cannot_satisfy_mandatory_self_review() -> None:
    events = [
        AgentEvent(
            run_id="run-1",
            sequence=1,
            event_type="quality.validation_recorded",
            payload={
                "success": True,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-1",
            },
        ),
        AgentEvent(
            run_id="run-1",
            sequence=2,
            event_type="model.message",
            payload={"phase": "message_end", "text": _structured_payload()},
        ),
        AgentEvent(
            run_id="run-1",
            sequence=3,
            event_type="quality.stage",
            payload={
                "stage": "self_review",
                "attempt": 1,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-1",
            },
        ),
    ]

    assert _self_review_response_from_repository(
        _Repository(events),
        run_id="run-1",
        attempt=1,
        task_revision_id="revision-1",
        workspace_state_id="state-1",
    ) == ""


def test_self_review_response_requires_exact_workspace_state_marker() -> None:
    old_payload = _structured_payload().replace("checked", "old-state")
    current_payload = _structured_payload().replace("checked", "current-state")
    events = [
        AgentEvent(
            run_id="run-1",
            sequence=1,
            event_type="quality.stage",
            payload={
                "stage": "self_review",
                "attempt": 1,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-old",
            },
        ),
        AgentEvent(
            run_id="run-1",
            sequence=2,
            event_type="model.message",
            payload={"phase": "message_end", "text": old_payload},
        ),
        AgentEvent(
            run_id="run-1",
            sequence=3,
            event_type="quality.stage",
            payload={
                "stage": "self_review",
                "attempt": 1,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-current",
            },
        ),
        AgentEvent(
            run_id="run-1",
            sequence=4,
            event_type="model.message",
            payload={"phase": "message_end", "text": current_payload},
        ),
    ]

    repository = _Repository(events)
    assert _self_review_response_from_repository(
        repository,
        run_id="run-1",
        attempt=1,
        task_revision_id="revision-1",
        workspace_state_id="state-current",
    ) == current_payload
    assert _self_review_response_from_repository(
        repository,
        run_id="run-1",
        attempt=1,
        task_revision_id="revision-1",
        workspace_state_id="state-old",
    ) == ""


def test_post_marker_structured_json_is_accepted_as_self_review_response() -> None:
    payload = _structured_payload()
    events = [
        AgentEvent(
            run_id="run-1",
            sequence=1,
            event_type="quality.stage",
            payload={
                "stage": "self_review",
                "attempt": 2,
                "task_revision_id": "revision-1",
                "workspace_state_id": "state-1",
            },
        ),
        AgentEvent(
            run_id="run-1",
            sequence=2,
            event_type="model.message",
            payload={"phase": "message_end", "text": payload},
        ),
    ]

    assert _self_review_response_from_repository(
        _Repository(events),
        run_id="run-1",
        attempt=2,
        task_revision_id="revision-1",
        workspace_state_id="state-1",
    ) == payload
