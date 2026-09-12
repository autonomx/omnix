from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.agent_runtime import review_orchestration
from app.agent_runtime.candidate_test_validation import missing_candidate_test_execution
from app.agent_runtime.contracts import ValidationResult


def _validation(command: str, *, state: str = "state-final") -> ValidationResult:
    return ValidationResult(
        result_id=f"result-{len(command)}-{state}",
        run_id="run-1",
        validation_id="final-state-tests",
        kind="test",
        task_revision_id="rev-1",
        workspace_state_id=state,
        command=command,
        exit_code=0,
        success=True,
        outcome="passed",
        output_digest="digest",
        finished_at=datetime.now(timezone.utc),
    )


def test_broad_playwright_does_not_claim_vitest_unit_test() -> None:
    unit = "src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx"
    e2e = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
    missing = missing_candidate_test_execution(
        [unit, e2e],
        [_validation("npx playwright test")],
        workspace_state_id="state-final",
    )
    assert missing == [unit]


def test_generic_npm_test_does_not_claim_separate_e2e_tree() -> None:
    unit = "src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx"
    e2e = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
    missing = missing_candidate_test_execution(
        [unit, e2e],
        [_validation("npm --prefix src/apps/web test")],
        workspace_state_id="state-final",
    )
    assert missing == [e2e]


def test_deleted_run_owned_test_is_not_an_execution_obligation(tmp_path: Path) -> None:
    deleted = "tests/test_removed_feature.py"
    assert missing_candidate_test_execution(
        [deleted],
        [],
        workspace_state_id="state-final",
        workspace_root=str(tmp_path),
    ) == []


def test_existing_snapshot_test_remains_an_execution_obligation(tmp_path: Path) -> None:
    path = "tests/test_new_feature.py"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text("def test_new_feature():\n    assert True\n", encoding="utf-8")
    assert missing_candidate_test_execution(
        [path],
        [],
        workspace_state_id="state-final",
        workspace_root=str(tmp_path),
    ) == [path]


def test_reviewer_launch_checks_candidate_test_gate_first(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def redirect(_service, parent_run_id: str, snapshot_id: str) -> bool:
        calls.append((parent_run_id, snapshot_id))
        return True

    monkeypatch.setattr(review_orchestration, "_redirect_missing_candidate_tests_before_review", redirect)
    review_orchestration.launch_reviewer_children(object(), "parent-1", "snapshot-1", 1)
    assert calls == [("parent-1", "snapshot-1")]
