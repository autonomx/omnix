from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# If a model voluntarily declares an impact candidate as MODIFY, preserve
# internal structural closure without making candidate classification mandatory.
replace_once(
    "src/app/agent_runtime/planning.py",
    '''        if disposition.disposition == "modify":
            candidate = candidate_map[disposition.candidate_id]
            linked = [item for item in submission.changes if candidate.candidate_id in item.candidate_ids]
            if linked and not any(
                _path_matches(path, candidate.path)
                for item in linked
                for path in item.paths
            ):
                failures.append(f"impact_modify_path_not_planned:{candidate.candidate_id}:{candidate.path}")
''',
    '''        if disposition.disposition == "modify":
            candidate = candidate_map[disposition.candidate_id]
            linked = [item for item in submission.changes if candidate.candidate_id in item.candidate_ids]
            if not linked:
                failures.append(f"impact_modify_not_linked_to_plan_item:{candidate.candidate_id}")
            elif not any(
                _path_matches(path, candidate.path)
                for item in linked
                for path in item.paths
            ):
                failures.append(f"impact_modify_path_not_planned:{candidate.candidate_id}:{candidate.path}")
''',
)

# Preserve useful capability/managed-preview guarantees in the concise Pi loop.
replace_once(
    "src/app/agent_runtime/pi_runtime.py",
    '''Omnix capability, workspace, approval, budget, and external-system policies remain independently authoritative.
If Omnix explicitly blocks a consequential operation because hard planning authority is required''',
    '''Omnix capability, workspace, approval, budget, and external-system policies remain independently authoritative. The capabilities listed under `Issued governed external capabilities` are already issued; when one is needed, invoke it through `omnix_capability` rather than asking the user to grant it again.
If Omnix explicitly blocks a consequential operation because hard planning authority is required''',
)
replace_once(
    "src/app/agent_runtime/pi_runtime.py",
    '''For governed UI validation, use `omnix_capability` with `browser.open` and `{\"workspace_preview\": true, \"path\": \"/<route>\"}`; do not launch a separate Vite/dev server through the shell.
Pi settling is only a completion request.''',
    '''For governed UI validation, use `omnix_capability` with `browser.open` and `{\"workspace_preview\": true, \"path\": \"/<route>\"}`; do not launch a separate Vite/dev server through the shell. After a passing deterministic browser assertion, Omnix automatically tears down the workspace preview and browser session.
Pi settling is only a completion request.''',
)

# Old tests that asserted the orchestration we deliberately removed now assert
# the new Pi/intelligence vs Omnix/invariants boundary.
replace_once(
    "src/tests/agent_runtime/test_coding_quality_final_hardening.py",
    '''def test_structured_self_review_is_required_and_state_bound(tmp_path: Path) -> None:
''',
    '''def test_legacy_structured_self_review_remains_readable_but_is_not_acceptance_authority(tmp_path: Path) -> None:
''',
)
replace_once(
    "src/tests/agent_runtime/test_coding_quality_final_hardening.py",
    '''    assert "quality_self_review_stale_or_missing" in quality_failure_reasons(snapshot, revision, state, [], [], [self_review.model_copy(update={"workspace_state_id":"old"})])
''',
    '''    assert "quality_self_review_stale_or_missing" not in quality_failure_reasons(snapshot, revision, state, [], [], [self_review.model_copy(update={"workspace_state_id":"old"})])
''',
)

replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    '''def test_pi_remains_guarded_but_receives_mandatory_engineering_workflow(tmp_path: Path) -> None:
''',
    '''def test_pi_remains_guarded_but_owns_the_engineering_loop(tmp_path: Path) -> None:
''',
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

replace_once(
    "src/tests/agent_runtime/test_evidence_backed_planning.py",
    '''    evidence, candidates, _ = build_inspection_bundle(
        spec,
        revision,
        paths=["src/apps/web/ChatIdentityModeControl.tsx"],
    )
''',
    '''    evidence, candidates, _ = build_inspection_bundle(
        spec,
        revision,
        queries=["Character settings"],
        paths=["src/apps/web/ChatIdentityModeControl.tsx"],
    )
''',
)

Path("src/tests/agent_runtime/test_planning_repair_protocol.py").write_text(
    '''from __future__ import annotations\n\nfrom app.agent_runtime.coding_quality import repair_prompt\nfrom app.agent_runtime.contracts import ReviewFinding, ReviewResult, TaskRevision\n\n\ndef test_quality_repair_returns_reasoning_to_pi_and_hard_gates_only_when_required() -> None:\n    revision = TaskRevision(\n        revision_id="revision-plan-repair",\n        run_id="run-plan-repair",\n        sequence=1,\n        user_instruction="Fix the regression",\n        effective_objective="Fix the regression",\n    )\n    review = ReviewResult(\n        run_id=revision.run_id,\n        reviewer_run_id="reviewer-1",\n        review_snapshot_id="snapshot-1",\n        task_revision_id=revision.revision_id,\n        workspace_state_id="state-1",\n        verdict="changes_required",\n        findings=[\n            ReviewFinding(\n                severity="high",\n                category="correctness",\n                problem="A caller still uses the old behavior.",\n                recommended_fix="Update the caller and regression coverage.",\n            )\n        ],\n    )\n\n    prompt = repair_prompt(revision, review, [], attempt=2)\n\n    assert "continue the normal Pi inspect/reason/edit/test loop" in prompt\n    assert "Ordinary in-scope repair edits do not require a PlanDelta" in prompt\n    assert "explicitly blocks a consequential operation" in prompt\n    assert "omnix_plan" in prompt\n    assert "Before ANY repair mutation" not in prompt\n''',
    encoding="utf-8",
)

replace_once(
    "src/tests/agent_runtime/test_planning_runtime_contract.py",
    '''def test_engineering_prompt_requires_durable_plan_before_mutation(tmp_path: Path) -> None:
''',
    '''def test_engineering_prompt_makes_normal_working_plan_advisory(tmp_path: Path) -> None:
''',
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
    '''    assert gate == "self_review"
''',
    '''    assert gate == "ready"
''',
)

print("agent de-orchestration follow-up applied")
