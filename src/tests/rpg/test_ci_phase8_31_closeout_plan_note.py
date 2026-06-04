from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase8_closeout_plan.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_31_closeout_plan_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow


def test_phase8_31_closeout_plan_records_bounded_final_checklist():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 8 has reached closeout planning after Phase 8.30.",
        "Remaining Phase 8 work is capped at four final slices.",
        "Phase 8.32 — Panel contract inventory and consolidation",
        "Phase 8.33 — Browser smoke coverage for registered panels",
        "Phase 8.34 — UI runtime-authority boundary audit",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff",
        "Do not add more Phase 8 metadata-only families after Phase 8.31.",
        "Phase 9 — 1000-turn endurance systems",
    ):
        assert expected in plan
