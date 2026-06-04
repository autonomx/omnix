from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_24_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_24_completion_note_records_panel_chrome_freshness_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.24 panel chrome freshness metadata is complete.",
        "Implementation PR: #272",
        "1857a48e8fa6464cc585b77303e28234919124f0",
        "5fba6a6131a7c6abeb0d9bc359031d6fc923d6ff",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "payload freshness metadata",
        "live, missing, snapshot, and stale panel payload states",
        "freshness metadata",
        "Metadata-only UI polish",
        "does not validate payload age at runtime",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_24_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
