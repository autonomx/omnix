from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime import chat_bridge
from app.agent_runtime.chat_bridge import route_typed_chat_turn
from app.agent_runtime.semantic_task import (
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
)
from app.agent_runtime.semantic_task_parser import classify_semantic_task_safely


class _WorkspaceContextSensitiveParser:
    def __init__(self, *, fail_recovery: bool = False) -> None:
        self.fail_recovery = fail_recovery
        self.reference_contexts: list[str] = []
        self.last_diagnostics: dict[str, object] = {}

    def parse_contextual(
        self,
        _content: str,
        *,
        reference_context: str = "",
        previous_objective: str = "",
        current_environment: dict[str, object] | None = None,
        deadline_at: float | None = None,
    ) -> SemanticTask:
        del previous_objective, current_environment, deadline_at
        self.reference_contexts.append(reference_context)
        if reference_context or self.fail_recovery:
            self.last_diagnostics = {
                "error_type": "StructuredOutputExhausted",
                "error": "semantic output was invalid with the full Chat context",
            }
            raise RuntimeError("semantic parse failed")
        self.last_diagnostics = {
            "provider": "fake",
            "cache_hit": False,
        }
        return SemanticTask(
            intent="fix attached workspace button spacing",
            subjects=[
                SemanticSubject(
                    target="workspace",
                    reference="Omnix chat button spacing",
                    kind="software_ui",
                )
            ],
            operations=[
                SemanticOperation(
                    kind="inspect",
                    target="workspace",
                    subject_reference="Omnix chat button spacing",
                ),
                SemanticOperation(
                    kind="modify",
                    target="workspace",
                    subject_reference="Omnix chat button spacing",
                ),
                SemanticOperation(
                    kind="validate",
                    target="workspace",
                    subject_reference="Omnix chat button spacing",
                ),
            ],
            workspace_surfaces=["web_ui"],
            autonomous=True,
            multi_step=True,
            ambiguity="none",
            confidence=0.98,
            reason_code="workspace_ui_fix",
        )


def test_safe_semantic_parse_retries_without_chat_history_for_active_workspace() -> None:
    parser = _WorkspaceContextSensitiveParser()

    task = classify_semantic_task_safely(
        parser,
        "fix the omnix chat full screen button spacing",
        reference_context="User: stale unrelated conversation context",
        current_environment={
            "active_workspace": "omnix",
            "workspace_source": "turn_attachment",
            "workspace_attached_this_turn": True,
        },
    )

    assert task is not None
    assert task.operations[1].kind == "modify"
    assert task.operations[1].target == "workspace"
    assert parser.reference_contexts == [
        "User: stale unrelated conversation context",
        "",
    ]
    assert parser.last_diagnostics["context_retry_attempted"] is True
    assert (
        parser.last_diagnostics["context_retry_reason"]
        == "active_workspace_context_reduction"
    )
    assert parser.last_diagnostics["context_retry_succeeded"] is True
    assert (
        parser.last_diagnostics["context_retry_initial_error_type"]
        == "StructuredOutputExhausted"
    )


def test_workspace_context_recovery_still_fails_closed_when_second_parse_fails() -> None:
    parser = _WorkspaceContextSensitiveParser(fail_recovery=True)

    task = classify_semantic_task_safely(
        parser,
        "fix the omnix chat full screen button spacing",
        reference_context="User: stale unrelated conversation context",
        current_environment={"active_workspace": "omnix"},
    )

    assert task is None
    assert parser.reference_contexts == [
        "User: stale unrelated conversation context",
        "",
    ]
    assert parser.last_diagnostics["context_retry_attempted"] is True
    assert parser.last_diagnostics["context_retry_succeeded"] is False


def test_workspace_context_recovery_does_not_strip_active_objective_context() -> None:
    parser = _WorkspaceContextSensitiveParser()

    task = classify_semantic_task_safely(
        parser,
        "fix it",
        reference_context="User: the button is still too close",
        previous_objective='{"canonical_request":"fix button spacing"}',
        current_environment={"active_workspace": "omnix"},
    )

    assert task is None
    assert parser.reference_contexts == ["User: the button is still too close"]
    assert "context_retry_attempted" not in parser.last_diagnostics


def test_chat_route_recovers_workspace_agent_instead_of_parser_unavailable_error(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    started = []
    parser = _WorkspaceContextSensitiveParser()

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(
        id="workspace-context-recovery",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="workspace-context-recovery-message",
        role="user",
        content="fix the omnix chat full screen button spacing in the attached workspace",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=parser,
        routing_context_factory=lambda: "User: stale unrelated conversation context",
    )

    assert result is not None
    assert result.metadata["omnix_route"]["lane"] == "agent"
    assert result.metadata["agent_run"]["profile"] == "coding"
    assert len(started) == 1
    assert started[0].workspace is not None
    assert started[0].workspace.root == str(selected.resolve())
    assert "workspace.edit" in started[0].capabilities
    assert parser.reference_contexts == [
        "User: stale unrelated conversation context",
        "",
    ]
    parser_diagnostics = result.metadata["routing_decision"]["parser"]
    assert parser_diagnostics["context_retry_attempted"] is True
    assert parser_diagnostics["context_retry_succeeded"] is True


def test_chat_route_keeps_fail_closed_behavior_when_workspace_recovery_fails(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    parser = _WorkspaceContextSensitiveParser(fail_recovery=True)

    class _Service:
        def start(self, _spec):
            raise AssertionError("failed semantic recovery must not start an Agent")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(
        id="workspace-context-fail-closed",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="workspace-context-fail-closed-message",
        role="user",
        content="fix the omnix chat full screen button spacing in the attached workspace",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=parser,
        routing_context_factory=lambda: "User: stale unrelated conversation context",
    )

    assert result is not None
    assert result.metadata["semantic_gate"]["accepted"] is False
    assert result.metadata["semantic_gate"]["reason"] == "semantic_parser_unavailable"
    assert "won't guess" in result.content
    assert parser.reference_contexts == [
        "User: stale unrelated conversation context",
        "",
    ]
