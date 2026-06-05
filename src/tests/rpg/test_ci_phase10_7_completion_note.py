from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_7_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_7_production_readiness_closeout_decision_gate.md"


def test_phase10_7_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.7 production readiness closeout decision gate is complete.",
        "Implementation PR: #327",
        "4b86fe3269bffc57b85953fd6950f2c44ea0a80a",
        "045a8755736535211848caa0950a888d3bca43c7",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_7_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free production readiness closeout decision gate",
        "classifies the current state as `production_closeout_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_7_completion_note_matches_closeout_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase10_evidence_index",
        "package_evidence_status",
        "install_run_status",
        "persistence_status",
        "diagnostics_status",
        "player_safe_error_status",
        "release_candidate_status",
        "operator_intake_status",
        "production_closeout_evidence_gap",
        "production_release_ready",
    ):
        assert expected in plan
    for expected in (
        "Phase 10 evidence index",
        "package evidence status",
        "install/run status",
        "persistence status",
        "diagnostics status",
        "player-safe error status",
        "release candidate status",
        "operator intake status",
        "production_closeout_evidence_gap",
        "production_release_ready",
    ):
        assert expected in note
