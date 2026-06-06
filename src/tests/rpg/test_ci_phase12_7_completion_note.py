from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_7_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_7_completion_note_records_bundle():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.7 is complete as an evidence intake closeout and implementation handoff gate",
        "bundled Phase 12.7 evidence intake closeout, completion note, tests, and roadmap advancement in one PR by request",
        "aedd4be8e82d7f428d5df2e964ef31007384cd87",
        "docs/plans/rpg_phase12_7_evidence_intake_closeout.md",
        "src/tests/rpg/test_ci_phase12_7_evidence_intake_closeout.py",
        "docs/plans/rpg_phase12_7_completion_note.md",
        "src/tests/rpg/test_ci_phase12_7_completion_note.py",
    ):
        assert expected in note


def test_phase12_7_completion_note_records_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_7_no_accepted_evidence`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase13_implementation_blocked`",
        "selected Phase 13 implementation target: none",
        "No concrete Phase 13 implementation target has been selected",
        "Production readiness is not claimable",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in note


def test_roadmap_advances_to_phase13_1_after_phase12_7():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.",
        "Current slice: **Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached**.",
        "Latest source-of-truth SHA before Phase 13.1: `aedd4be8e82d7f428d5df2e964ef31007384cd87`.",
        "- [x] Phase 12.7 — accepted evidence intake closeout or implementation handoff.",
        "- [ ] Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached.",
        "Phase 13.1 scope:",
        "Do not implement speculative hardening without accepted evidence.",
    ):
        assert expected in roadmap
