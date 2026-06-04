from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_7_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_7_operator_evidence_intake_contract.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase9_7_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.7 operator evidence intake contract is complete.",
        "Implementation PR: #308",
        "5fbf4e0fbcab03b263d28addd8749855a4d22a1b",
        "d3f00250efdef5898cc23e7cf94a936875939837",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase9_7_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free contract",
        "without requiring a live/provider 100-turn or 1000-turn campaign in CI",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "operator_evidence_gap",
    ):
        assert expected in note


def test_phase9_7_completion_note_matches_operator_evidence_contract():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "run_metadata",
        "provider_model_config",
        "artifact_bundle_paths",
        "timing_metrics",
        "save_load_checkpoint_evidence",
        "package_disk_replay_evidence",
        "progress_quality_review",
        "continuity_review",
        "taxonomy_classification",
        "missing timing evidence should classify as `operator_evidence_gap`",
        "missing transcript review should classify as `operator_evidence_gap`",
    ):
        assert expected in plan
    for expected in (
        "run metadata",
        "provider/model/config",
        "artifact bundle paths",
        "timing metrics",
        "save/load checkpoint evidence",
        "package/disk replay evidence",
        "progress-quality review",
        "continuity review",
        "taxonomy classification",
    ):
        assert expected in note


def test_phase9_7_roadmap_and_architecture_workflow_are_aligned():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 9.8 — long-run continuity evidence envelope**.",
        "Next recommended slice after Phase 9.8: **Phase 9.9 — targeted endurance hardening from concrete evidence**.",
        "Phase 9.1 through Phase 9.7 are complete",
        "Phase 9.8 scope:",
        "Phase 9.7 — operator evidence intake contract.",
        "#308 Phase 9.7 operator evidence intake contract",
        "d3f00250efdef5898cc23e7cf94a936875939837",
    ):
        assert expected in roadmap
    for expected in (
        "src/tests/rpg/test_ci_phase9_7_operator_evidence_intake_contract.py",
        "src/tests/rpg/test_ci_phase9_7_completion_note.py",
        "docs/plans/rpg_phase9_7_operator_evidence_intake_contract.md",
        "docs/plans/rpg_phase9_7_completion_note.md",
    ):
        assert expected in workflow
