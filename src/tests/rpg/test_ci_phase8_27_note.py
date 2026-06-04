from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_27_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_27_completion_note_records_panel_chrome_provenance_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.27 panel chrome provenance metadata is complete.",
        "Implementation PR: #278",
        "80e9020f6f75e7b3f2951467fdb64daa71453e2c",
        "5c0fde5f2545acfbd0793b82243b369cce7f20f4",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "provenance metadata",
        "chrome, layout_registry, payload, and runtime_contract provenance",
        "Metadata-only UI polish",
        "does not introduce a component framework",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_27_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
