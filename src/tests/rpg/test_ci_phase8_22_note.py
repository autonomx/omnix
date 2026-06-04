from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_22_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_22_completion_note_records_panel_chrome_focus_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.22 panel chrome focus metadata is complete.",
        "Implementation PR: #268",
        "f53d2caac7422e5cd49d9f6f43701e96c072b083",
        "f248ede26806728d5242cb06a5fdfa814c8402a5",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "stable panel focus target constant",
        "focus attribute rendering",
        "DOM metadata helpers",
        "keyboard/focus styling and tests",
        "imperative focus behavior",
        "not a full UI overhaul",
    ):
        assert expected in note


def test_phase8_22_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_22_note.py" in workflow
    assert "docs/plans/rpg_phase8_22_completion_note.md" in workflow
