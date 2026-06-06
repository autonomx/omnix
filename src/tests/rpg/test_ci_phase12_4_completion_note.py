from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_4_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_4_completion_note_records_bundle():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.4 is complete as a player-safe error/redaction evidence-decision gate",
        "bundled Phase 12.4 evidence decision, completion note, tests, and roadmap advancement in one PR by request",
        "40306cda83207fd003b2a82b7f2e57efcf5b2bb3",
        "docs/plans/rpg_phase12_4_player_safe_error_redaction_evidence_decision.md",
        "src/tests/rpg/test_ci_phase12_4_player_safe_error_redaction_evidence_decision.py",
        "docs/plans/rpg_phase12_4_completion_note.md",
        "src/tests/rpg/test_ci_phase12_4_completion_note.py",
    ):
        assert expected in note


def test_phase12_4_completion_note_records_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_4_player_safe_error_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_4_implementation_blocked`",
        "selected player-safe error/redaction fix target: none",
        "No concrete player-safe error or redaction hardening fix has been implemented",
        "Production readiness is not claimable",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in note


def test_roadmap_advances_to_phase12_5_after_phase12_4():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 12.5 — live/provider endurance evidence capture or hardening**.",
        "Latest source-of-truth SHA before Phase 12.5: `40306cda83207fd003b2a82b7f2e57efcf5b2bb3`.",
        "- [x] Phase 12.4 — player-safe error/redaction evidence capture or hardening.",
        "- [ ] Phase 12.5 — live/provider endurance evidence capture or hardening.",
        "Phase 12.5 scope:",
        "Do not implement speculative endurance hardening without accepted live/provider endurance evidence.",
    ):
        assert expected in roadmap
