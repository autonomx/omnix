from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_4_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_4_persistence_diagnostics_evidence_runbook.md"


def test_phase11_4_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.4 persistence and diagnostics evidence capture runbook is complete.",
        "Implementation PR: #335",
        "fd3bcf35c244f25bfcb954cade938bfc00c463d8",
        "f89796ea864397d6fc47510d11a1541b1d7d97aa",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_4_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator runbook",
        "persistence_diagnostics_capture_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_4_completion_note_matches_runbook_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "persistence_diagnostics_capture_not_started",
        "save_path_capture_gap",
        "session_path_capture_gap",
        "data_path_capture_gap",
        "save_load_roundtrip_capture_gap",
        "saved_state_artifact_gap",
        "diagnostic_log_capture_gap",
        "diagnostic_bundle_capture_gap",
        "persistence_diagnostics_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "save/session/data/report path snapshots",
        "save/load roundtrip steps and result",
        "replay artifact capture",
        "diagnostic log capture",
        "diagnostic bundle manifest",
        "Phase 11.5 — first player-safe error and redaction evidence capture runbook",
    ):
        assert expected in note
