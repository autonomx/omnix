from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_21_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_21_completion_note_records_panel_chrome_read_only_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.21 panel chrome read-only metadata is complete.",
        "Implementation PR: #266",
        "f2e4af619ce9990af8840f7f92a92e48bf372fc8",
        "86a7c4027d62e58a0726b21e2b100caaabb2ec1e",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "stable read-only authority constant",
        "read-only attribute rendering",
        "DOM metadata helpers",
        "presentation-only/read-only",
        "runtime-authority boundaries",
        "not a full UI overhaul",
    ):
        assert expected in note


def test_phase8_21_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_21_note.py" in workflow
    assert "docs/plans/rpg_phase8_21_completion_note.md" in workflow
