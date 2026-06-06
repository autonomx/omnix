from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_6_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_6_completion_note_records_bundle():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.6 is complete as a checkpoint/replay evidence-decision gate",
        "bundled Phase 12.6 evidence decision, completion note, tests, and roadmap advancement in one PR by request",
        "f063a53996d3e2c5801c84220172f4b8d580e533",
        "docs/plans/rpg_phase12_6_checkpoint_replay_evidence_decision.md",
        "src/tests/rpg/test_ci_phase12_6_checkpoint_replay_evidence_decision.py",
        "docs/plans/rpg_phase12_6_completion_note.md",
        "src/tests/rpg/test_ci_phase12_6_completion_note.py",
    ):
        assert expected in note


def test_phase12_6_completion_note_records_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_6_checkpoint_replay_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_6_implementation_blocked`",
        "selected checkpoint/replay fix target: none",
        "No concrete checkpoint or replay hardening fix has been implemented",
        "Production readiness is not claimable",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in note


def test_roadmap_advances_to_phase12_7_after_phase12_6():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 12.7 — accepted evidence intake closeout or implementation handoff**.",
        "Latest source-of-truth SHA before Phase 12.7: `f063a53996d3e2c5801c84220172f4b8d580e533`.",
        "- [x] Phase 12.6 — checkpoint/replay evidence capture or hardening.",
        "- [ ] Phase 12.7 — accepted evidence intake closeout or implementation handoff.",
        "Phase 12.7 scope:",
        "Do not implement speculative hardening without accepted evidence.",
    ):
        assert expected in roadmap
