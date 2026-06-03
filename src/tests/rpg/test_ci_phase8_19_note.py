from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_19_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_19_completion_note_records_panel_chrome_accessibility_polish():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.19 panel chrome accessibility polish is complete.",
        "Implementation PR: #262",
        "1d5839e496aa8a52729d3c57990742b05928a12b",
        "1ebb1f153bbfe4642eb4923c5caa1e1b4423249a",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "source-backed panel chrome labels",
        "runtime validation notices",
        "deterministic accessibility source metadata",
        "not a full UI overhaul",
    ):
        assert expected in note


def test_phase8_19_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_19_note.py" in workflow
    assert "docs/plans/rpg_phase8_19_completion_note.md" in workflow
