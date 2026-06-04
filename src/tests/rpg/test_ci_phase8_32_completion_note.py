from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_32_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_32_completion_note_records_panel_contract_inventory():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.32 panel contract inventory is complete.",
        "Implementation PR: #288",
        "4efbdf097da6cf4c9617a547948293ce8c30e87c",
        "ae5955f6c8b96c41c5a32c1227ac1e80f2bfda86",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "nine registered Phase 8 panel slots",
        "Shared layout registry contract inventory",
        "Shared RpgPanelChrome contract inventory",
        "Consolidated list of existing Phase 8 metadata families",
        "Stop condition against adding another metadata-only family",
        "Documentation/source-guard only",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_32_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
