from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime.candidate_test_validation import (
    candidate_test_validation_specs,
    executable_candidate_test_paths,
    missing_candidate_test_execution,
)
from app.agent_runtime.contracts import AgentEvent, ValidationResult


def _validation(command: str, *, state: str = "state-final", success: bool = True) -> ValidationResult:
    return ValidationResult(
        result_id=f"validation-{abs(hash((command, state, success)))}",
        run_id="run-1",
        validation_id="final-state-tests",
        kind="test",
        task_revision_id="rev-1",
        workspace_state_id=state,
        command=command,
        exit_code=0 if success else 1,
        success=success,
        outcome="passed" if success else "substantive_failure",
        output_digest="digest",
        finished_at=datetime.now(timezone.utc),
    )


def _started(sequence: int, call_id: str, command: str, *, tool: str = "bash") -> AgentEvent:
    return AgentEvent(
        run_id="run-1",
        sequence=sequence,
        event_type="tool.started",
        payload={"tool_call_id": call_id, "tool": tool, "args": {"command": command}},
    )


def _completed(sequence: int, call_id: str, *, tool: str = "bash", exit_code: int = 0) -> AgentEvent:
    return AgentEvent(
        run_id="run-1",
        sequence=sequence,
        event_type="tool.completed",
        payload={
            "tool_call_id": call_id,
            "tool": tool,
            "is_error": exit_code != 0,
            "result": {"exitCode": exit_code},
        },
    )


def test_executable_candidate_test_paths_are_narrow_and_exclude_support_files() -> None:
    paths = executable_candidate_test_paths(
        [
            "src/apps/web/tests/e2e/chatbot-layout.spec.ts",
            "src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx",
            "tests/test_service.py",
            "pkg/engine_test.go",
            "src/apps/web/tests/helpers.ts",
            "src/apps/web/tests/fixtures/page.ts",
            "src/apps/web/src/__snapshots__/ChatbotWorkspace.test.tsx.snap",
            "src/apps/web/playwright.config.ts",
            "tests/conftest.py",
        ]
    )
    assert paths == [
        "pkg/engine_test.go",
        "src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx",
        "src/apps/web/tests/e2e/chatbot-layout.spec.ts",
        "tests/test_service.py",
    ]


def test_targeted_unit_test_does_not_cover_new_playwright_regression() -> None:
    subject = [
        "src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx",
        "src/apps/web/tests/e2e/chatbot-layout.spec.ts",
    ]
    missing = missing_candidate_test_execution(
        subject,
        [_validation("npm --prefix src/apps/web test -- ChatbotWorkspace.test.tsx")],
        workspace_state_id="state-final",
    )
    assert missing == ["src/apps/web/tests/e2e/chatbot-layout.spec.ts"]


def test_exact_targeted_playwright_validation_covers_run_owned_e2e_test() -> None:
    path = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
    missing = missing_candidate_test_execution(
        [path],
        [_validation("npx playwright test tests/e2e/chatbot-layout.spec.ts")],
        workspace_state_id="state-final",
    )
    assert missing == []


def test_broad_test_suite_covers_all_run_owned_tests_for_exact_state() -> None:
    subject = ["tests/test_service.py", "tests/test_review_runtime.py"]
    assert missing_candidate_test_execution(
        subject,
        [_validation("python -m pytest -q")],
        workspace_state_id="state-final",
    ) == []


def test_stale_success_does_not_cover_final_candidate() -> None:
    path = "tests/test_service.py"
    missing = missing_candidate_test_execution(
        [path],
        [_validation("python -m pytest -q tests/test_service.py", state="state-old")],
        workspace_state_id="state-final",
    )
    assert missing == [path]


def test_raw_playwright_success_after_last_mutation_is_accepted_for_legacy_classifier() -> None:
    path = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
    events = [
        _started(1, "edit-1", "", tool="edit"),
        _completed(2, "edit-1", tool="edit"),
        _started(3, "pw-1", "npx playwright test tests/e2e/chatbot-layout.spec.ts"),
        _completed(4, "pw-1"),
        _started(5, "diff-1", "git diff --check"),
        _completed(6, "diff-1"),
    ]
    assert missing_candidate_test_execution(
        [path],
        [],
        workspace_state_id="state-final",
        events=events,
    ) == []


def test_raw_playwright_success_before_later_edit_is_not_final_state_evidence() -> None:
    path = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
    events = [
        _started(1, "pw-1", "npx playwright test tests/e2e/chatbot-layout.spec.ts"),
        _completed(2, "pw-1"),
        _started(3, "edit-1", "", tool="edit"),
        _completed(4, "edit-1", tool="edit"),
    ]
    assert missing_candidate_test_execution(
        [path],
        [],
        workspace_state_id="state-final",
        events=events,
    ) == [path]


def test_candidate_validation_specs_are_deterministic_and_path_specific() -> None:
    path = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
    first = candidate_test_validation_specs([path])
    second = candidate_test_validation_specs([path])
    assert len(first) == 1
    assert first[0].id == second[0].id
    assert first[0].kind == "test"
    assert first[0].required is True
    assert path in first[0].description
    assert path in str(first[0].command_hint)
