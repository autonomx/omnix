from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = ROOT / "docs" / "plans" / "rpg_phase8_final_closeout_handoff.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_35_final_closeout_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow


def test_phase8_35_final_closeout_note_records_phase9_handoff():
    handoff = HANDOFF.read_text(encoding="utf-8")
    for expected in (
        "Phase 8 is complete as a provider-free UI/UX foundation pass.",
        "Phase 8.35 — final closeout note and Phase 9 handoff.",
        "Phase 9 — 1000-turn endurance systems",
        "Phase 9.1 — endurance harness baseline and failure taxonomy",
        "Do not add more Phase 8 slices unless a required gate exposes a concrete regression",
        "Phase 8 was not a full visual/gameplay UI overhaul.",
        "Future UI/UX work should either be:",
    ):
        assert expected in handoff
