from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.contracts import (
    AgentArtifact,
    AgentEvent,
    AgentRunSnapshot,
    AgentRunSpec,
    EvidenceReceipt,
    ModelRef,
    TaskRevision,
)
from app.agent_runtime.semantic_classifier import classify_semantic_intent_safely
from app.agent_runtime.service import AgentRunService


class _ExplodingClassifier:
    def classify(self, _content: str):
        raise TimeoutError("classifier timed out")


def test_classifier_failure_falls_back_without_raising() -> None:
    assert classify_semantic_intent_safely(
        _ExplodingClassifier(),
        "fix the tests",
    ) is None


def test_second_revision_ignores_untagged_tool_events() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="new task",
        effective_objective="new task",
    )
    untagged = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={"tool_call_id": "old"},
    )
    current = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={
            "tool_call_id": "new",
            "task_revision_id": revision.revision_id,
        },
    )
    assert AgentRunService._events_for_revision(
        [untagged, current],
        revision,
    ) == [current]


def test_first_revision_can_accept_legacy_untagged_tool_events() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=1,
        user_instruction="initial",
        effective_objective="initial",
    )
    untagged = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={"tool_call_id": "legacy"},
    )
    assert AgentRunService._events_for_revision([untagged], revision) == [untagged]


def test_second_revision_ignores_untagged_artifacts() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="new task",
        effective_objective="new task",
    )
    old = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="legacy.diff",
        metadata={},
    )
    current = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="current.diff",
        metadata={"task_revision_id": revision.revision_id},
    )
    assert AgentRunService._artifacts_for_revision(
        [old, current],
        revision,
    ) == [current]


def test_second_revision_ignores_prior_evidence_receipts() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="new task",
        effective_objective="new task",
    )
    old = EvidenceReceipt(
        run_id="run-1",
        task_revision_id="old",
        capability_id="research.web_search",
        source_class="general_current_web",
        request_digest="old",
        result_digest="old",
    )
    current = old.model_copy(
        update={
            "receipt_id": "current",
            "task_revision_id": revision.revision_id,
            "request_digest": "new",
            "result_digest": "new",
        }
    )
    assert AgentRunService._receipts_for_revision(
        [old, current],
        revision,
    ) == [current]


def test_parent_waits_until_all_children_terminal() -> None:
    class Repo:
        def list_children(self, _run_id):
            return [
                SimpleNamespace(status="completed"),
                SimpleNamespace(status="running"),
            ]

    terminal, failed = AgentRunService._children_terminal_state(Repo(), "parent")
    assert terminal is False
    assert failed is False


def test_parent_failure_propagates_when_any_child_failed() -> None:
    class Repo:
        def list_children(self, _run_id):
            return [
                SimpleNamespace(status="completed"),
                SimpleNamespace(status="failed"),
            ]

    terminal, failed = AgentRunService._children_terminal_state(Repo(), "parent")
    assert terminal is True
    assert failed is True


def test_parent_failure_propagates_when_child_cancelled() -> None:
    class Repo:
        def list_children(self, _run_id):
            return [
                SimpleNamespace(status="completed"),
                SimpleNamespace(status="cancelled"),
            ]

    terminal, failed = AgentRunService._children_terminal_state(Repo(), "parent")
    assert terminal is True
    assert failed is True


def test_superseding_run_contract_links_both_directions() -> None:
    old_spec = AgentRunSpec(
        run_id="old",
        task="old task",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    new_spec = AgentRunSpec(
        run_id="new",
        task="new task",
        model=ModelRef(provider_id="test", model_id="model"),
        supersedes_run_id="old",
    )
    old = AgentRunSnapshot(
        run_id="old",
        spec=old_spec,
        status="cancelled",
        superseded_by_run_id="new",
    )
    new = AgentRunSnapshot(
        run_id="new",
        spec=new_spec,
        status="running",
    )
    assert old.superseded_by_run_id == new.run_id
    assert new.spec.supersedes_run_id == old.run_id


def test_terminal_run_statuses_are_explicit_and_non_running() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="task",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    for status in ("completed", "failed", "cancelled"):
        snapshot = AgentRunSnapshot(
            run_id="run-1",
            spec=spec,
            status=status,
        )
        assert snapshot.status != "running"


def test_revision_chain_preserves_previous_revision_identity() -> None:
    first = TaskRevision(
        revision_id="rev-1",
        run_id="run-1",
        sequence=1,
        user_instruction="first",
        effective_objective="first",
    )
    second = TaskRevision(
        revision_id="rev-2",
        run_id="run-1",
        sequence=2,
        previous_revision_id=first.revision_id,
        user_instruction="second",
        effective_objective="second",
    )
    assert second.previous_revision_id == first.revision_id
    assert second.sequence == first.sequence + 1
