from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_23_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_23_completion_note_records_panel_chrome_section_metadata():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.23 panel chrome section metadata is complete.",
        "Implementation PR: #270",
        "ec69b23d68f5e7ff34b1fad11475fb406d454ec2",
        "ba6fdfa8b13d8acfb7a142f1c36908c4afd36201",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "RpgPanelChrome",
        "deterministic density metadata",
        "compact and normal styling hooks",
        "root, header, body, and footer panel regions",
        "section/density metadata",
        "without adding behavior",
        "not a full UI overhaul",
    ):
        assert expected in note


def test_phase8_23_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_23_note.py" in workflow
    assert "docs/plans/rpg_phase8_23_completion_note.md" in workflow
