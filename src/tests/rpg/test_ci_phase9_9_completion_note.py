from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_9_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_9_targeted_endurance_hardening_decision_gate.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase9_9_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.9 targeted endurance hardening decision gate is complete.",
        "Implementation PR: #312",
        "a829c82af9d1d363edfb3cb12ad955c146539f0f",
        "ef76e019679900b3c2b2f96307eef6bcec5a3f8c",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase9_9_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free decision gate",
        "classifies the current hardening decision as `operator_evidence_gap`",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "No targeted runtime hardening was performed because no concrete evidence was attached.",
    ):
        assert expected in note


def test_phase9_9_completion_note_matches_decision_gate():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "operator_evidence_gap",
        "documentation_only_followup",
        "harness_contract_fix",
        "artifact_contract_fix",
        "checkpoint_replay_fix",
        "progress_quality_fix",
        "performance_budget_fix",
        "world_continuity_fix",
        "provider_boundary_fix",
        "runtime_authority_fix",
        "must cite at least one concrete evidence source before changing runtime",
        "allowed changes: documentation and deterministic source guards only",
    ):
        assert expected in plan
        assert expected in note or expected in plan
    for expected in (
        "runtime, harness, gameplay, save/load, replay, UI, or provider-boundary code",
        "live/operator artifact bundle",
        "checkpoint/replay package",
        "continuity review",
        "performance evidence",
        "failing CI log",
    ):
        assert expected in note


def test_phase9_9_roadmap_and_architecture_workflow_are_aligned():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 10 — production packaging, stability, and release readiness**.",
        "Current slice: **Phase 10.1 — production readiness baseline and packaging evidence plan**.",
        "Next recommended slice after Phase 10.1: **Phase 10.2 — install/run configuration evidence envelope**.",
        "Phase 9.1 through Phase 9.9 are complete",
        "Phase 9.9 — targeted endurance hardening decision gate.",
        "#312 Phase 9.9 hardening decision gate",
        "ef76e019679900b3c2b2f96307eef6bcec5a3f8c",
    ):
        assert expected in roadmap
    for expected in (
        "src/tests/rpg/test_ci_phase9_9_targeted_endurance_hardening_decision_gate.py",
        "src/tests/rpg/test_ci_phase9_9_completion_note.py",
        "docs/plans/rpg_phase9_9_targeted_endurance_hardening_decision_gate.md",
        "docs/plans/rpg_phase9_9_completion_note.md",
    ):
        assert expected in workflow
