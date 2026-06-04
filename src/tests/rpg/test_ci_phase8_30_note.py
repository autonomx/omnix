from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_30_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_30_completion_note_records_panel_chrome_surface_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.30 panel chrome surface metadata is complete.",
        "Implementation PR: #284",
        "67cc6ec9cae88d4ffb60a9272ae8ef97907c8898",
        "21cd44f262d326e87eb7774e9a6025adc06674b9",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "surface metadata",
        "PANEL_SURFACES constants for badge, empty, notice, and panel surfaces",
        "panelChromeSurface, surfaceAttrs, and applySurfaceMetadata helpers",
        "Metadata-only UI polish",
        "does not introduce a component framework",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_30_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
