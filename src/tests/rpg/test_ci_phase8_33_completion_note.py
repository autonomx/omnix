from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_33_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_33_completion_note_records_browser_smoke_coverage():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.33 browser smoke coverage is complete.",
        "Implementation PR: #290",
        "9975dd5767b456719010a3f4411935f2b53cc818",
        "ebb654f47ce23d6d51d07e84f3f26434c3416643",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "nine registered Phase 8 panels",
        "shared chrome usage across registered panels",
        "escaped dynamic rendering expectations",
        "provider-free and runtime-safe panel behavior",
        "does not install a new browser test harness",
        "Phase 8.34 authority audit",
        "Phase 8.35 final closeout/handoff",
    ):
        assert expected in note


def test_phase8_33_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
