from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_6_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_6_targeted_endurance_hardening.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase9_6_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.6 targeted endurance hardening plan is complete.",
        "Implementation PR: #306",
        "4b260a600a02f1dcbde102e651e6346d5e800be9",
        "90aaf03214071d93b693bc5c41b484350b89d2fb",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "docs/plans/rpg_phase9_6_targeted_endurance_hardening.md",
        "docs/plans/rpg_production_readiness_plan.md",
        "src/tests/rpg/test_ci_phase9_6_targeted_endurance_hardening.py",
        "Phase 9.7 — operator evidence intake contract",
    ):
        assert expected in note


def test_phase9_6_completion_note_aligns_with_plan_and_roadmap():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    for expected in (
        "targeted endurance hardening",
        "concrete evidence",
        "operator_evidence_gap",
        "Phase 9.7 — operator evidence intake contract",
    ):
        assert expected in note
        assert expected in plan

    for expected in (
        "Phase 8 — UI/UX Production Pass: **Closed as provider-free UI/UX foundation**.",
        "Phase 9 — 1000-Turn Endurance Systems: **In progress; Phase 9.1 through Phase 9.5 complete; Phase 9.6 current**.",
        "Next recommended slice after Phase 9.6: **Phase 9.7 — operator evidence intake contract**.",
    ):
        assert expected in roadmap
