from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime.api import StartAgentRunRequest
from app.agent_runtime.coding_quality import (
    candidate_validation_gate,
    diff_review_command_is_complete,
    parse_review_result,
    review_is_acceptable,
    validation_result_from_tool_event,
)
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSpec,
    ModelRef,
    ReviewSnapshot,
    TaskRequirement,
    TaskRevision,
    ValidationResult,
    ValidationSpec,
)
from app.agent_runtime.service import _quality_sized_run_spec


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="rev-1",
        run_id="run-1",
        sequence=1,
        user_instruction="fix",
        effective_objective="fix",
        requirements=[TaskRequirement(id="R", description="fix", required=True)],
        validation_plan=[ValidationSpec(id="final-state-tests", kind="test", description="tests", covers=["R"])],
    )


def _validation(outcome: str, *, digest: str = "x") -> ValidationResult:
    return ValidationResult(
        result_id=f"result-{outcome}-{digest}",
        run_id="run-1",
        validation_id="final-state-tests",
        kind="test",
        task_revision_id="rev-1",
        workspace_state_id="state-1",
        command="pytest",
        exit_code=0 if outcome == "passed" else 1,
        success=outcome == "passed",
        outcome=outcome,
        output_digest=digest,
        covers_requirement_ids=["R"],
        finished_at=datetime.now(timezone.utc),
    )


def test_shell_git_diff_is_never_final_diff_authority() -> None:
    assert not diff_review_command_is_complete("git diff HEAD")
    assert not diff_review_command_is_complete("git diff --no-ext-diff")


def test_run_change_set_tool_is_bound_to_exact_candidate() -> None:
    revision = TaskRevision(
        revision_id="rev-1", run_id="run-1", sequence=1,
        user_instruction="fix", effective_objective="fix",
        validation_plan=[ValidationSpec(id="final-diff-review", kind="diff_review", description="diff")],
    )
    result = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1",
            event_type="tool.completed",
            payload={
                "tool": "omnix_change_set",
                "tool_call_id": "cs-1",
                "is_error": False,
                "result": {"details": {"change_set": {"change_set_id": "cs", "candidate_workspace_state_id": "state-1"}}},
            },
        ),
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1", revision=revision,
    )
    assert result is not None
    assert result.validation_id == "final-diff-review"
    assert result.outcome == "passed"


def test_candidate_validation_gate_does_not_use_quality_attempt_identity() -> None:
    revision = _revision()
    gate, rows = candidate_validation_gate(revision, [_validation("substantive_failure")], workspace_state_id="state-1")
    assert gate == "validation_repair"
    assert rows and rows[0].workspace_state_id == "state-1"
    gate, _ = candidate_validation_gate(revision, [_validation("infrastructure_failure")], workspace_state_id="state-1")
    assert gate == "validation_retry"
    gate, _ = candidate_validation_gate(revision, [_validation("passed")], workspace_state_id="state-1")
    assert gate == "passed"


def test_server_downgrades_baseline_only_high_finding_to_nonblocking_context() -> None:
    snapshot = ReviewSnapshot(
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1",
        base_commit_sha="abc", patch_checksum="def", run_change_set_id="cs-1",
        workspace_root="/tmp/review", subject_paths=["src/styles.css"], context_paths=["src/repository.py"],
    )
    revision = _revision()
    text = '''{"verdict":"approve","requirements":[{"requirement_id":"R","status":"satisfied","evidence":"ok"}],"findings":[{"severity":"high","category":"correctness","file":"src/repository.py","location":null,"problem":"baseline issue","recommended_fix":null,"subject_paths":["src/repository.py"],"context_paths":[]}],"missing_tests":[],"residual_risks":[]}'''
    result = parse_review_result(text, parent_run_id="run-1", reviewer_run_id="reviewer", snapshot=snapshot)
    finding = result.findings[0]
    assert finding.attribution == "baseline_context"
    assert not finding.blocking
    assert review_is_acceptable(result, revision)


def test_dependency_finding_blocks_only_when_it_names_run_owned_subject() -> None:
    snapshot = ReviewSnapshot(
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1",
        base_commit_sha="abc", patch_checksum="def", run_change_set_id="cs-1",
        workspace_root="/tmp/review", subject_paths=["src/api.py"], context_paths=["src/repository.py"],
    )
    revision = _revision()
    text = '''{"verdict":"changes_required","requirements":[{"requirement_id":"R","status":"satisfied","evidence":"ok"}],"findings":[{"severity":"high","category":"correctness","file":"src/repository.py","location":null,"problem":"API change breaks baseline caller","recommended_fix":null,"subject_paths":["src/api.py"],"context_paths":["src/repository.py"]}],"missing_tests":[],"residual_risks":[]}'''
    result = parse_review_result(text, parent_run_id="run-1", reviewer_run_id="reviewer", snapshot=snapshot)
    assert result.findings[0].attribution == "run_owned_dependency"
    assert result.findings[0].blocking
    assert not review_is_acceptable(result, revision)


def test_api_limits_omitted_and_null_are_not_explicit_but_empty_object_is() -> None:
    common = dict(task="fix", provider_id="chatgpt_codex", model_id="gpt-5.6-luna", profile="coding")
    omitted = StartAgentRunRequest(**common)
    explicit_null = StartAgentRunRequest(**common, limits=None)
    explicit_empty = StartAgentRunRequest(**common, limits={})
    assert omitted.limits is None
    assert explicit_null.limits is None
    assert explicit_empty.limits is not None and explicit_empty.limits.max_steps == 200

    implicit_spec = AgentRunSpec(
        task="fix", model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna"),
        profile="coding", expected_artifacts=["diff"], quality_policy="strict",
    )
    explicit_spec = implicit_spec.model_copy(update={"limits": explicit_empty.limits})
    # model_copy does not change fields_set, so reconstruct to represent HTTP explicit intent.
    explicit_spec = AgentRunSpec(**{**implicit_spec.model_dump(), "limits": explicit_empty.limits.model_dump()})
    assert _quality_sized_run_spec(implicit_spec).limits.max_steps == 500
    assert _quality_sized_run_spec(explicit_spec).limits.max_steps == 200


def test_run_card_keeps_unreported_tokens_distinct_from_zero() -> None:
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "apps/web/src/features/chatbot/OmnixRunCardCore.tsx").read_text(encoding="utf-8")
    assert "if (reported !== true) return '—';" in source
    assert "input_tokens_reported" in source
    assert "output_tokens_reported" in source
    assert "Not reported" in source


def test_baseline_only_changes_required_verdict_is_nonblocking_after_server_attribution() -> None:
    snapshot = ReviewSnapshot(
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1",
        base_commit_sha="abc", patch_checksum="def", run_change_set_id="cs-1",
        workspace_root="/tmp/review", subject_paths=["src/styles.css"], context_paths=["src/repository.py"],
    )
    result = parse_review_result(
        '{"verdict":"changes_required","requirements":[{"requirement_id":"R","status":"satisfied","evidence":"ok"}],"findings":[{"severity":"high","category":"correctness","file":"src/repository.py","location":null,"problem":"baseline issue","recommended_fix":null,"subject_paths":[],"context_paths":["src/repository.py"]}],"missing_tests":[],"residual_risks":[]}',
        parent_run_id="run-1", reviewer_run_id="reviewer", snapshot=snapshot,
    )
    assert result.findings[0].attribution == "baseline_context"
    assert result.findings[0].blocking is False
    assert review_is_acceptable(result, _revision())


def test_latest_same_candidate_validation_result_is_authoritative() -> None:
    revision = _revision()
    passed = _validation("passed", digest="pass")
    failed = _validation("substantive_failure", digest="fail").model_copy(
        update={"finished_at": passed.finished_at.replace(microsecond=min(999999, passed.finished_at.microsecond + 1))}
    )
    gate, rows = candidate_validation_gate(revision, [passed, failed], workspace_state_id="state-1")
    assert gate == "validation_repair"
    assert rows and rows[0].output_digest == "fail"
