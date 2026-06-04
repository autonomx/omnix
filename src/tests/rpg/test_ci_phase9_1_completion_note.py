from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_1_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase9_1_completion_note_records_endurance_baseline():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.1 endurance harness baseline and failure taxonomy is complete.",
        "Implementation PR: #296",
        "69b48f60c0b55ab6784c7ccafdfb4ea8f1a0ee99",
        "d598b976b6add027cbbe58b269f7bb3da2080024",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "src/tests/rpg/autoplay_llm_campaign.py",
        "summary, transcript, and ZIP outputs",
        "Deterministic endurance failure taxonomy",
        "CI-gated versus operator/manual evidence boundaries",
        "runtime_part27",
        "runtime_part23",
        "Phase 9.2 — deterministic endurance artifact contract guard",
    ):
        assert expected in note


def test_phase9_1_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase9_1_endurance_baseline.py" in workflow
    assert "docs/plans/rpg_phase9_1_endurance_baseline.md" in workflow
