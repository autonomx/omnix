from __future__ import annotations

from app.agent_runtime.coding_quality import diff_review_command_is_complete, validation_result_from_tool_event
from app.agent_runtime.contracts import AgentEvent, TaskRevision, ValidationSpec


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1", run_id="run-1", sequence=1,
        user_instruction="Fix the UI", effective_objective="Fix the UI",
        validation_plan=[ValidationSpec(id="final-diff-review", kind="diff_review", description="Inspect authoritative run change set")],
    )


def test_shell_diff_is_inspection_context_not_completion_authority() -> None:
    for command in (
        "git diff --no-ext-diff", "git diff HEAD", "git diff -- src/apps/web/src/styles.css",
        "git diff --name-only", "git diff --stat",
    ):
        assert not diff_review_command_is_complete(command)
        result = validation_result_from_tool_event(
            AgentEvent(
                run_id="run-1", event_type="tool.completed",
                payload={"tool_call_id": "call", "args": {"command": command}, "result": {"details": {"exitCode": 0}}},
            ),
            run_id="run-1", task_revision_id="revision-1", workspace_state_id="state-1", revision=_revision(),
        )
        assert result is None


def test_authoritative_change_set_tool_must_match_candidate_state() -> None:
    good = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1", event_type="tool.completed",
            payload={"tool": "omnix_change_set", "tool_call_id": "cs", "result": {"details": {"change_set": {"change_set_id": "one", "candidate_workspace_state_id": "state-1"}}}},
        ),
        run_id="run-1", task_revision_id="revision-1", workspace_state_id="state-1", revision=_revision(),
    )
    assert good is not None and good.success and good.outcome == "passed"
    stale = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1", event_type="tool.completed",
            payload={"tool": "omnix_change_set", "tool_call_id": "cs2", "result": {"details": {"change_set": {"change_set_id": "old", "candidate_workspace_state_id": "state-old"}}}},
        ),
        run_id="run-1", task_revision_id="revision-1", workspace_state_id="state-1", revision=_revision(),
    )
    assert stale is not None and not stale.success and stale.outcome == "protocol_failure"
