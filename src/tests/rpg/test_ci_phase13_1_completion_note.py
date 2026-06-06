from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase13_1_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase13_1_completion_note_records_bundle():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 13.1 is complete as an operator evidence backfill reopen gate",
        "bundled Phase 13.1 evidence backfill reopen, completion note, tests, and roadmap advancement in one PR by request",
        "fa0cee3ae42ab26be49eb00d3d17d3c7d13ed604",
        "docs/plans/rpg_phase13_1_operator_evidence_backfill_reopen.md",
        "src/tests/rpg/test_ci_phase13_1_operator_evidence_backfill_reopen.py",
        "docs/plans/rpg_phase13_1_completion_note.md",
        "src/tests/rpg/test_ci_phase13_1_completion_note.py",
    ):
        assert expected in note


def test_phase13_1_completion_note_records_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase13_1_no_accepted_evidence`",
        "secondary classification: `operator_evidence_backfill_reopened`",
        "implementation state: `phase13_implementation_blocked`",
        "selected implementation target: none",
        "No concrete Phase 13 implementation target has been selected",
        "Production readiness is not claimable",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in note


def test_roadmap_advances_to_phase13_2_after_phase13_1():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.",
        "Current slice: **Phase 13.2 — first accepted hardening target implementation after evidence attachment**.",
        "Latest source-of-truth SHA before Phase 13.2: `fa0cee3ae42ab26be49eb00d3d17d3c7d13ed604`.",
        "- [x] Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached.",
        "- [ ] Phase 13.2 — first accepted hardening target implementation after evidence attachment.",
        "Phase 13.2 scope:",
        "Do not implement speculative hardening without accepted evidence.",
    ):
        assert expected in roadmap
