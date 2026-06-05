from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_1_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_1_evidence_driven_hardening_triage.md"


def test_phase11_1_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.1 evidence-driven production hardening triage is complete.",
        "Implementation PR: #329",
        "4b0c8995777b52132c5162449acb66a2f1e1c119",
        "33bc5ce073b027a213ba28eec56f198fd2e14d25",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_1_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free production hardening triage contract",
        "hardening_evidence_gap",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_1_completion_note_matches_triage_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "hardening_evidence_gap",
        "operator_evidence_backfill_required",
        "ci_failure_hardening_target",
        "operator_artifact_hardening_target",
        "source_diagnostic_hardening_target",
        "runtime_hardening_ready",
        "packaging_hardening_ready",
        "diagnostics_hardening_ready",
        "player_safe_error_hardening_ready",
        "release_candidate_review_ready",
    ):
        assert expected in plan
    for expected in (
        "operator artifacts",
        "CI failure logs",
        "source-backed diagnostics",
        "operator evidence backfill remains pending",
        "Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures",
    ):
        assert expected in note
