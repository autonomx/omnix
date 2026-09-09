from __future__ import annotations

import threading

from app.agent_runtime.contracts import (
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
)
from app.agent_runtime.pi_runtime import PiAgentRuntime, normalize_pi_event


def _spec(run_id: str) -> AgentRunSpec:
    return AgentRunSpec(
        run_id=run_id,
        task="Finish validating the current coding change",
        objective="Finish validating the current coding change",
        profile="coding",
        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna"),
    )


def _usage_limit_payload(event_type: str) -> dict[str, object]:
    return {
        "type": event_type,
        "message": {
            "role": "assistant",
            "model": "chatgpt_codex::gpt-5.6-luna",
            "stopReason": "error",
            "errorMessage": (
                "ConnectionError: {'message': \"You've hit your usage limit. Try again later.\", "
                "'codexErrorInfo': 'usageLimitExceeded'}"
            ),
            "content": [],
        },
    }


def test_terminal_provider_usage_limit_becomes_explicit_run_failure() -> None:
    event = normalize_pi_event(
        "run-provider-limit-1",
        _usage_limit_payload("message_end"),
        task_revision_id="revision-1",
    )

    assert event is not None
    assert event.event_type == "run.failed"
    assert event.payload["provider_error_code"] == "model_usage_limit_exceeded"
    assert event.payload["task_revision_id"] == "revision-1"
    assert str(event.payload["error"]).startswith("model_usage_limit_exceeded:")


def test_local_omnix_budget_error_keeps_run_scope_and_is_not_rate_limit() -> None:
    event = normalize_pi_event(
        "run-local-budget-1",
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "stopReason": "error",
                "errorMessage": (
                    "HTTP 409: {'detail': {'type': 'agent_budget_error', "
                    "'code': 'budget_max_steps_exceeded', 'retryable': false, 'scope': 'run'}}"
                ),
                "content": [],
            },
        },
        task_revision_id="revision-budget",
    )

    assert event is not None
    assert event.event_type == "run.failed"
    assert event.payload["provider_error_code"] == "agent_run_budget_exhausted"
    assert event.payload["retryable"] is False
    assert event.payload["error_scope"] == "run"
    assert "model_rate_limit_exceeded" not in str(event.payload["error"])


def test_duplicate_turn_end_and_settle_after_provider_failure_are_suppressed() -> None:
    run_id = "run-provider-limit-duplicate"

    first = normalize_pi_event(run_id, _usage_limit_payload("message_end"))
    duplicate = normalize_pi_event(run_id, _usage_limit_payload("turn_end"))
    settle = normalize_pi_event(run_id, {"type": "agent_settled"})

    assert first is not None
    assert first.event_type == "run.failed"
    assert duplicate is None
    assert settle is None


def test_intentional_request_abort_is_not_reclassified_as_provider_failure() -> None:
    event = normalize_pi_event(
        "run-intentional-abort",
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "stopReason": "aborted",
                "errorMessage": "Request aborted",
                "content": [],
            },
        },
    )

    assert event is not None
    assert event.event_type == "model.message"


def test_normal_terminal_assistant_message_is_still_model_message() -> None:
    event = normalize_pi_event(
        "run-normal-message",
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "stopReason": "stop",
                "content": [{"type": "text", "text": "Validation passed."}],
            },
        },
    )

    assert event is not None
    assert event.event_type == "model.message"
    assert event.payload["text"] == "Validation passed."


def test_stalled_recovery_steers_fresh_active_turn_without_abort_or_second_prompt() -> None:
    actions: list[tuple[str, str]] = []

    class Session:
        _turn_active = True

        def steer(self, message: str, **_kwargs) -> None:
            actions.append(("steer", message))

        def abort(self) -> None:
            actions.append(("abort", ""))

        def prompt(self, message: str, **_kwargs) -> None:
            actions.append(("prompt", message))

    spec = _spec("run-stalled-recovery-active")
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: Session()}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(
            run_id=spec.run_id,
            spec=spec,
            status="resume_requested",
        )
    }

    result = runtime.command_with_context(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="resume",
            payload={
                "message": "Recover the validating stage from durable state.",
                "recovery_attempt": 1,
            },
        )
    )

    assert result.status == "running"
    assert len(actions) == 1
    assert actions[0][0] == "steer"
    assert "Recover the validating stage from durable state." in actions[0][1]


def test_stalled_recovery_prompts_normally_when_session_is_already_idle() -> None:
    actions: list[tuple[str, str]] = []

    class Session:
        _turn_active = False

        def steer(self, message: str, **_kwargs) -> None:
            actions.append(("steer", message))

        def prompt(self, message: str, **_kwargs) -> None:
            actions.append(("prompt", message))

    spec = _spec("run-stalled-recovery-idle")
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: Session()}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="resume_requested")
    }

    runtime.command_with_context(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="resume",
            payload={"message": "Resume validation.", "recovery_attempt": 2},
        )
    )

    assert len(actions) == 1
    assert actions[0][0] == "prompt"
    assert "Resume validation." in actions[0][1]


def test_self_review_recovery_keeps_interrupted_turn_abort_then_prompt_semantics() -> None:
    actions: list[tuple[str, str]] = []

    class Session:
        _turn_active = True

        def abort(self) -> None:
            actions.append(("abort", ""))

        def prompt(self, message: str, **_kwargs) -> None:
            actions.append(("prompt", message))

    spec = _spec("run-self-review-recovery")
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: Session()}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="resume_requested")
    }

    runtime.command_with_context(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="resume",
            payload={
                "message": (
                    "This is an internal quality/self-review turn that did not finish its protocol. "
                    "Return ONLY the required structured verdict JSON."
                ),
                "recovery_attempt": 1,
            },
        )
    )

    assert [action for action, _ in actions] == ["abort", "prompt"]

def test_bare_omnix_gateway_409_is_preserved_as_run_budget_exhaustion() -> None:
    event = normalize_pi_event(
        "run-local-budget-bare-409",
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "provider": "omnix",
                "stopReason": "error",
                "errorMessage": "409 status code (no body)",
                "content": [],
            },
        },
        task_revision_id="revision-budget-409",
    )
    assert event is not None
    assert event.event_type == "run.failed"
    assert event.payload["provider_error_code"] == "agent_run_budget_exhausted"
    assert event.payload["retryable"] is False
    assert event.payload["error_scope"] == "run"
