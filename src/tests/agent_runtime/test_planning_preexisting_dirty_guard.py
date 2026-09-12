from __future__ import annotations

from app.agent_runtime.planning_api import (
    _plan_next_action,
    _preexisting_dirty_operation_failures,
    _preexisting_dirty_plan_failures,
)
from app.agent_runtime.planning_contracts import ImplementationPlanSubmission, PlanItem


_DIRTY_TEST = "src/apps/web/tests/e2e/chatbot-layout.spec.ts"
_BASELINE = {
    "head": "a" * 40,
    "dirty_paths": [
        ".kilo/",
        _DIRTY_TEST,
    ],
    "dirty_digests": {
        ".kilo/": "__directory__",
        _DIRTY_TEST: "digest-before-run",
    },
}


def _submission(*, path: str = _DIRTY_TEST, effects: list[str] | None = None) -> ImplementationPlanSubmission:
    return ImplementationPlanSubmission(
        changes=[
            PlanItem(
                id="extend-chat-layout-regression",
                intent="Extend the regression coverage",
                paths=[path],
                allowed_effects=effects or ["mutate"],
            )
        ]
    )


def test_plan_rejects_mutation_of_test_that_was_dirty_before_run() -> None:
    failures = _preexisting_dirty_plan_failures(_submission(), _BASELINE)
    assert failures == [
        "plan_mutates_preexisting_dirty_path:extend-chat-layout-regression:"
        + _DIRTY_TEST
    ]
    assert "do not modify paths that were already dirty" in _plan_next_action("rejected", failures)


def test_plan_rejects_directory_pattern_covering_preexisting_dirty_path() -> None:
    failures = _preexisting_dirty_plan_failures(
        _submission(path="src/apps/web/tests/e2e/**"),
        _BASELINE,
    )
    assert failures == [
        "plan_mutates_preexisting_dirty_path:extend-chat-layout-regression:"
        + _DIRTY_TEST
    ]


def test_plan_allows_nonmutating_reference_to_preexisting_dirty_path() -> None:
    assert _preexisting_dirty_plan_failures(
        _submission(effects=["validate"]),
        _BASELINE,
    ) == []


def test_operation_blocks_edit_before_preexisting_dirty_content_is_overwritten() -> None:
    assert _preexisting_dirty_operation_failures(
        effect="mutate",
        target_path=_DIRTY_TEST,
        command="",
        baseline_provenance=_BASELINE,
    ) == [f"preexisting_dirty_path_mutation_forbidden:{_DIRTY_TEST}"]


def test_operation_allows_clean_target_and_validation_of_dirty_target() -> None:
    assert _preexisting_dirty_operation_failures(
        effect="mutate",
        target_path="src/apps/web/src/features/chatbot/ChatbotWorkspaceSidePanelFix.css",
        command="",
        baseline_provenance=_BASELINE,
    ) == []
    assert _preexisting_dirty_operation_failures(
        effect="validate",
        target_path=_DIRTY_TEST,
        command="npm --prefix src/apps/web run test:e2e -- tests/e2e/chatbot-layout.spec.ts",
        baseline_provenance=_BASELINE,
    ) == []
