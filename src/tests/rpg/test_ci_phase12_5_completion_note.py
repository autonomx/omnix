from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_5_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_5_completion_note_records_bundle():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.5 is complete as an endurance evidence-decision gate",
        "bundled Phase 12.5 evidence decision, completion note, tests, and roadmap advancement in one PR by request",
        "891822cedd5ceee44e8f2bc012b2f803bd8c57bd",
        "docs/plans/rpg_phase12_5_endurance_evidence_decision.md",
        "src/tests/rpg/test_ci_phase12_5_endurance_evidence_decision.py",
        "docs/plans/rpg_phase12_5_completion_note.md",
        "src/tests/rpg/test_ci_phase12_5_completion_note.py",
    ):
        assert expected in note


def test_phase12_5_completion_note_records_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_5_endurance_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_5_implementation_blocked`",
        "selected endurance fix target: none",
        "No concrete endurance hardening fix has been implemented",
        "Production readiness is not claimable",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in note


def test_roadmap_advances_to_phase12_6_after_phase12_5():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 12.6 — checkpoint/replay evidence capture or hardening**.",
        "Latest source-of-truth SHA before Phase 12.6: `891822cedd5ceee44e8f2bc012b2f803bd8c57bd`.",
        "- [x] Phase 12.5 — live/provider endurance evidence capture or hardening.",
        "- [ ] Phase 12.6 — checkpoint/replay evidence capture or hardening.",
        "Phase 12.6 scope:",
        "Do not implement speculative checkpoint or replay hardening without accepted checkpoint/replay evidence.",
    ):
        assert expected in roadmap
