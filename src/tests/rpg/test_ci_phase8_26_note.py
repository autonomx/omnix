from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_26_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_26_completion_note_records_panel_chrome_render_kind_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.26 panel chrome render-kind metadata is complete.",
        "Implementation PR: #276",
        "97c8f6b99ff82867349cc6394463119dd9b969f6",
        "c45a64f340bf8f154fa4bf5294e1c6edcbf04a4a",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "render-kind metadata",
        "badge, empty_state, notice, and panel render kinds",
        "Metadata-only UI polish",
        "does not introduce a component framework",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_26_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
