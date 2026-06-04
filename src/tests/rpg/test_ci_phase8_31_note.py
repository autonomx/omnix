from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_31_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_31_completion_note_records_closeout_plan():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.31 closeout planning is complete.",
        "Implementation PR: #286",
        "152288ea708048d32781607df6804fa1cca4b61d",
        "1fbfd87bf691408c901ae75f39eca7c107d9f415",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "Phase 8 closeout plan",
        "Phase 8.32 through Phase 8.35",
        "stop condition against more open-ended metadata-only Phase 8 families",
        "Phase 9 entry criteria",
        "provider-free UI/UX foundation pass",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_31_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
