from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_25_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_25_completion_note_records_panel_chrome_priority_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.25 panel chrome priority metadata is complete.",
        "Implementation PR: #274",
        "49a2eb1375a68993d8c9cf7359b64cb9f36683d1",
        "95ff5283c7d5d7b5c2cfcf4f9cce5357ac4543e3",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "priority metadata",
        "critical, high, low, and normal panel priority states",
        "Metadata-only UI polish",
        "does not decide gameplay or action urgency",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_25_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
