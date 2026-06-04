from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_28_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_28_completion_note_records_panel_chrome_tone_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.28 panel chrome tone metadata is complete.",
        "Implementation PR: #280",
        "59e36f340b72d67c5dfa15de93a6f8db12ba6da1",
        "94f7c9d5110cd718924d802e6438b9538caa5118",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "tone metadata",
        "info, muted, neutral, and warning tones",
        "Metadata-only UI polish",
        "does not introduce a component framework",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_28_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
