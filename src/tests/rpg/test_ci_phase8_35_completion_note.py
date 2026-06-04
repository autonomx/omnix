from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_35_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_35_completion_note_records_final_closeout_and_phase9_handoff():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.35 final closeout and Phase 9 handoff is complete.",
        "Implementation PR: #294",
        "552c90cd7a06a2785890d0fd3eb8c27ef2d4448c",
        "dad90d0257c7d9ce1dcb572ffd733a691a52a8a6",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "Phase 8 is complete as a provider-free UI/UX foundation pass",
        "Phase 8.31 through Phase 8.35",
        "Phase 9 handoff to 1000-turn endurance systems",
        "Phase 9.1 starting slice: endurance harness baseline and failure taxonomy",
        "Phase 8 is complete.",
        "Next phase is Phase 9 — 1000-turn endurance systems.",
    ):
        assert expected in note


def test_phase8_35_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
