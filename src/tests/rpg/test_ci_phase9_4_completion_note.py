from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_4_completion_note.md"
TAXONOMY = ROOT / "docs" / "plans" / "rpg_phase9_4_progress_quality_loop_taxonomy.md"
BRIDGE = ROOT / "src" / "tests" / "rpg" / "test_ci_phase9_2_completion_note.py"


def test_phase9_4_completion_note_records_guard():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.4 progress-quality loop taxonomy guard is complete.",
        "Implementation PR: #302",
        "6a4aa9d7c92bfff139402fa9205bf31b66cacc23",
        "a50978c140a333983fef93cf49d8115ef94d43e7",
        "progress_quality_failure",
        "turn_execution_failure",
        "operator_evidence_gap",
        "Phase 9.5 — endurance performance/evidence envelope",
    ):
        assert expected in note


def test_phase9_4_completion_note_aligns_with_taxonomy_and_bridge():
    note = NOTE.read_text(encoding="utf-8")
    taxonomy = TAXONOMY.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")

    assert "progress_quality_failure" in note
    assert "progress_quality_failure" in taxonomy
    assert "rpg_phase9_4_progress_quality_loop_taxonomy.md" in bridge
