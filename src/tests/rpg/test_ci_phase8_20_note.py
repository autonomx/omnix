from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_20_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_20_completion_note_records_panel_chrome_state_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.20 panel chrome state metadata is complete.",
        "Implementation PR: #264",
        "2eb6b328f4cd7658187a35aa585b64e8b7161c84",
        "20e9f88410b853ac6190ddacf4627278f9bca557",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "stable panel state constants",
        "state attribute rendering",
        "DOM state application helpers",
        "runtime validation notices",
        "deterministic state metadata",
        "not a full UI overhaul",
    ):
        assert expected in note


def test_phase8_20_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_20_note.py" in workflow
    assert "docs/plans/rpg_phase8_20_completion_note.md" in workflow
