from __future__ import annotations

from app.agent_runtime.coding_quality import (
    diff_review_command_is_complete,
    validation_result_from_tool_event,
)
from app.agent_runtime.contracts import AgentEvent, TaskRevision, ValidationSpec


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1",
        run_id="run-1",
        sequence=1,
        user_instruction="Fix the UI",
        effective_objective="Fix the UI",
        validation_plan=[
            ValidationSpec(
                id="final-diff-review",
                kind="diff_review",
                description="Inspect complete final diff",
                required=True,
            )
        ],
    )


def _result(command: str):
    return validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1",
            event_type="tool.completed",
            payload={
                "tool_call_id": "call-1",
                "args": {"command": command},
                "result": {"details": {"exitCode": 0, "output": "diff"}},
                "is_error": False,
            },
        ),
        run_id="run-1",
        task_revision_id="revision-1",
        workspace_state_id="state-1",
        revision=_revision(),
    )


def test_complete_diff_commands_are_authoritative_validation() -> None:
    assert diff_review_command_is_complete("git diff --no-ext-diff")
    assert diff_review_command_is_complete("git diff HEAD")
    result = _result("git diff --no-ext-diff")
    assert result is not None and result.success


def test_path_scoped_diff_cannot_satisfy_final_diff_review() -> None:
    assert not diff_review_command_is_complete("git diff -- src/apps/web/src/styles.css")
    assert not diff_review_command_is_complete("git diff src/app/agent_runtime/repository.py")
    result = _result("git diff -- src/apps/web/src/styles.css")
    assert result is not None
    assert not result.success
    assert result.metadata["failure_class"] == "incomplete_diff_scope"


def test_summary_only_diff_cannot_satisfy_final_diff_review() -> None:
    assert not diff_review_command_is_complete("git diff --name-only")
    assert not diff_review_command_is_complete("git diff --stat")
