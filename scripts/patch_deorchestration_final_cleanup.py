from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Fail closed when the planning-mode environment value is invalid. A typo must
# never silently downgrade consequential-mutation authority to shadow mode.
replace_once(
    "src/app/agent_runtime/planning.py",
    '    return value if value in {"off", "shadow", "enforce"} else "shadow"  # type: ignore[return-value]\n',
    '    return value if value in {"off", "shadow", "enforce"} else "enforce"  # type: ignore[return-value]\n',
)

# Final acceptance uses the new consequential-only conformance failure name.
replace_once(
    "src/app/agent_runtime/planning_acceptance.py",
    '            or failure.startswith("unplanned_modified_path:")\n',
    '            or failure.startswith("unplanned_consequential_path:")\n',
)
replace_once(
    "src/tests/agent_runtime/test_planning_acceptance.py",
    '        "unplanned_modified_path:src/unplanned.py",\n',
    '        "unplanned_consequential_path:package-lock.json",\n',
)

# Commit the six legacy-test updates that were verified in the prior runner but
# accidentally omitted from its git-add list.
replace_once(
    "src/tests/agent_runtime/test_coding_quality_final_hardening.py",
    'def test_structured_self_review_is_required_and_state_bound(tmp_path: Path) -> None:\n',
    'def test_legacy_structured_self_review_remains_readable_but_is_not_acceptance_authority(tmp_path: Path) -> None:\n',
)
replace_once(
    "src/tests/agent_runtime/test_coding_quality_final_hardening.py",
    '    assert "quality_self_review_stale_or_missing" in quality_failure_reasons(snapshot, revision, state, [], [], [self_review.model_copy(update={"workspace_state_id":"old"})])\n',
    '    assert "quality_self_review_stale_or_missing" not in quality_failure_reasons(snapshot, revision, state, [], [], [self_review.model_copy(update={"workspace_state_id":"old"})])\n',
)

replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    'def test_pi_remains_guarded_but_receives_mandatory_engineering_workflow(tmp_path: Path) -> None:\n',
    'def test_pi_remains_guarded_but_owns_the_engineering_loop(tmp_path: Path) -> None:\n',
)
replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    '''    assert "MANDATORY ENGINEERING WORKFLOW" in prompt
    assert "INSPECT THE COMPLETE RESULT" in prompt
    assert "FINAL-STATE VALIDATION" in prompt
    assert "Omnix allowlisted coding methodology skills" in prompt
''',
    '''    assert "PI-OWNED ENGINEERING LOOP" in prompt
    assert "working plan is informative rather than permission" in prompt
    assert "run required validation after the final mutation" in prompt
    assert "Trusted native Pi skill digest" in prompt
    assert "--skill" in argv
''',
)

Path("src/tests/agent_runtime/test_planning_repair_protocol.py").write_text(
    '''from __future__ import annotations\n\nfrom app.agent_runtime.coding_quality import repair_prompt\nfrom app.agent_runtime.contracts import ReviewFinding, ReviewResult, TaskRevision\n\n\ndef test_quality_repair_returns_reasoning_to_pi_and_hard_gates_only_when_required() -> None:\n    revision = TaskRevision(\n        revision_id="revision-plan-repair",\n        run_id="run-plan-repair",\n        sequence=1,\n        user_instruction="Fix the regression",\n        effective_objective="Fix the regression",\n    )\n    review = ReviewResult(\n        run_id=revision.run_id,\n        reviewer_run_id="reviewer-1",\n        review_snapshot_id="snapshot-1",\n        task_revision_id=revision.revision_id,\n        workspace_state_id="state-1",\n        verdict="changes_required",\n        findings=[\n            ReviewFinding(\n                severity="high",\n                category="correctness",\n                problem="A caller still uses the old behavior.",\n                recommended_fix="Update the caller and regression coverage.",\n            )\n        ],\n    )\n\n    prompt = repair_prompt(revision, review, [], attempt=2)\n\n    assert "continue the normal Pi inspect/reason/edit/test loop" in prompt\n    assert "Ordinary in-scope repair edits do not require a PlanDelta" in prompt\n    assert "explicitly blocks a consequential operation" in prompt\n    assert "omnix_plan" in prompt\n    assert "Before ANY repair mutation" not in prompt\n''',
    encoding="utf-8",
)

replace_once(
    "src/tests/agent_runtime/test_planning_runtime_contract.py",
    'def test_engineering_prompt_requires_durable_plan_before_mutation(tmp_path: Path) -> None:\n',
    'def test_engineering_prompt_makes_normal_working_plan_advisory(tmp_path: Path) -> None:\n',
)
replace_once(
    "src/tests/agent_runtime/test_planning_runtime_contract.py",
    '''    assert "omnix_plan" in prompt
    assert "action=`inspect`" in prompt
    assert "action=`submit`" in prompt
    assert "PLAN CONFORMANCE" in prompt
''',
    '''    assert "omnix_plan" in prompt
    assert "working plan is informative rather than permission" in prompt
    assert "Do not stop for a PlanDelta" in prompt
    assert "consequential operation" in prompt
    assert "PLAN CONFORMANCE" not in prompt
''',
)

replace_once(
    "src/tests/agent_runtime/test_quality_resume_recovery.py",
    '''            failures=("planning_base_commit_changed",),
        ),
    )

    service._finalize_acceptance(Repository(), current)

    service._quality_fail.assert_called_once()
''',
    '''            failures=("planning_base_commit_changed",),
            hard_gate_required=True,
        ),
    )

    service._finalize_acceptance(Repository(), current)

    service._quality_fail.assert_called_once()
''',
)

replace_once(
    "src/tests/agent_runtime/test_self_review_protocol_durability.py",
    '    assert gate == "self_review"\n',
    '    assert gate == "ready"\n',
)

# Explicit regressions for the two authority-review fixes.
path = Path("src/tests/agent_runtime/test_deorchestrated_pi_boundary.py")
text = path.read_text(encoding="utf-8")
text += '''\n\ndef test_invalid_planning_mode_fails_closed_to_enforce() -> None:\n    from app.agent_runtime.planning import planning_mode\n\n    assert planning_mode({"OMNIX_AGENT_PLANNING_MODE": "typo"}) == "enforce"\n\n\ndef test_unplanned_consequential_path_is_fail_closed_when_hard_gate_applies() -> None:\n    assessment = PlanningAcceptanceAssessment(\n        mode="enforce",\n        plan_revision_id="plan-1",\n        failures=("unplanned_consequential_path:package-lock.json",),\n        hard_gate_required=True,\n    )\n    assert assessment.blocks_acceptance\n    assert assessment.fail_closed\n'''
path.write_text(text, encoding="utf-8")

print("final de-orchestration cleanup applied")
