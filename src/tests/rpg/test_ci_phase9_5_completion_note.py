from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_5_completion_note.md"
ENVELOPE = ROOT / "docs" / "plans" / "rpg_phase9_5_performance_evidence_envelope.md"
BRIDGE = ROOT / "src" / "tests" / "rpg" / "test_ci_phase9_2_completion_note.py"


def test_phase9_5_completion_note_records_performance_evidence_envelope():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.5 performance evidence envelope is complete.",
        "Implementation PR: #304",
        "597aff1e436ab6a169c930e86bea75aaf9c09f00",
        "a6bb22007976dca1c0f3f92899cc05846588adf1",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "docs/plans/rpg_phase9_5_performance_evidence_envelope.md",
        "src/tests/rpg/test_ci_phase9_5_performance_evidence_envelope.py",
        "src/tests/rpg/test_ci_phase9_2_completion_note.py",
        "performance_budget_failure",
        "operator_evidence_gap",
        "progress_quality_failure",
        "No live/provider 1000-turn campaign added to CI.",
        "Phase 9.6 — targeted endurance hardening from concrete evidence",
    ):
        assert expected in note


def test_phase9_5_completion_note_aligns_with_envelope_and_bridge():
    note = NOTE.read_text(encoding="utf-8")
    envelope = ENVELOPE.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")

    for category in (
        "performance_budget_failure",
        "operator_evidence_gap",
        "progress_quality_failure",
    ):
        assert category in note
        assert category in envelope
    assert "rpg_phase9_5_performance_evidence_envelope.md" in bridge
    assert "Phase 9.6 — targeted endurance hardening from concrete evidence" in note
    assert "Phase 9.6 — targeted endurance hardening from concrete evidence" in envelope
