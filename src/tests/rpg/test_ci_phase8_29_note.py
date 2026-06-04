from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_29_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_29_completion_note_records_panel_chrome_schema_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.29 panel chrome schema metadata is complete.",
        "Implementation PR: #282",
        "02bb4fbe1ba601f374766d51aaef357cb31c238b",
        "921e30b6737d7bad1f807b8b253401b80ecf83b2",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "schema/version metadata",
        "PANEL_SCHEMA_VERSION",
        "panelChromeSchemaVersion, schemaAttrs, and applySchemaMetadata helpers",
        "Metadata-only UI polish",
        "does not introduce a component framework",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_29_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
