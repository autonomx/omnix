from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_7_evidence_intake_closeout.md"


def test_phase12_7_core_sections_and_sources():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.7 is the accepted evidence intake closeout or implementation handoff slice",
        "source/test/documentation only",
        "phase12_1_evidence_decision",
        "phase12_2_package_install_run_evidence_decision",
        "phase12_3_persistence_diagnostics_evidence_decision",
        "phase12_4_player_safe_error_redaction_evidence_decision",
        "phase12_5_endurance_evidence_decision",
        "phase12_6_checkpoint_replay_evidence_decision",
        "Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached",
    ):
        assert expected in plan


def test_phase12_7_handoff_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_evidence_source_path",
        "accepted_evidence_gate",
        "failure_category",
        "reproduction_command_or_steps",
        "affected_component",
        "severity",
        "player_or_operator_impact",
        "deterministic_runtime_boundary_impact",
        "proposed_bounded_fix_target",
        "explicit_non_targets",
        "acceptance_criteria",
        "required_verification_checks",
        "redaction_review",
        "handoff_owner_or_next_agent",
        "phase13_recommended_slice",
    ):
        assert expected in plan


def test_phase12_7_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_7_no_accepted_evidence",
        "operator_evidence_backfill_required",
        "accepted_evidence_incomplete",
        "package_install_run_handoff_ready",
        "persistence_diagnostics_handoff_ready",
        "player_safe_error_handoff_ready",
        "endurance_handoff_ready",
        "checkpoint_replay_handoff_ready",
        "phase13_implementation_handoff_ready",
        "phase13_implementation_blocked",
        "phase12_evidence_intake_closed_blocked",
    ):
        assert expected in plan


def test_phase12_7_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_7_no_accepted_evidence`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase13_implementation_blocked`",
        "selected Phase 13 implementation target: none",
        "documentation and deterministic source guards only",
        "runtime implementation",
        "provider implementation",
        "package implementation",
        "diagnostics implementation",
        "player-safe error implementation",
        "endurance implementation",
        "checkpoint/replay implementation",
        "provider calls",
        "LLM calls",
        "live 100-turn or 1000-turn CI execution",
        "package building in CI",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "Phase 13 implementation remains blocked without accepted evidence",
    ):
        assert expected in plan
