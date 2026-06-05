from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_1_evidence_decision.md"


def test_phase12_1_core_sections_and_evidence_categories():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.1 is the first concrete evidence-backed production hardening slice",
        "source/test/documentation only",
        "package_install_run_evidence",
        "persistence_diagnostics_evidence",
        "player_safe_error_redaction_evidence",
        "live_provider_100_turn_evidence",
        "live_provider_1000_turn_evidence",
        "checkpoint_replay_evidence",
        "ci_failure_logs",
        "source_backed_diagnostics",
        "Phase 12.2 — package/install/run evidence capture or hardening",
    ):
        assert expected in plan


def test_phase12_1_accepted_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_evidence_source_path",
        "evidence_category",
        "failure_category",
        "reproduction_command_or_steps",
        "affected_component",
        "severity",
        "player_impact",
        "deterministic_runtime_boundary_impact",
        "proposed_bounded_fix_target",
        "explicit_non_targets",
        "acceptance_criteria",
        "required_verification_checks",
        "redaction_review",
        "operator_or_source_diagnostic_reference",
    ):
        assert expected in plan


def test_phase12_1_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_1_no_accepted_evidence",
        "operator_evidence_backfill_required",
        "accepted_evidence_incomplete",
        "accepted_evidence_ready_for_runtime_fix",
        "accepted_evidence_ready_for_packaging_fix",
        "accepted_evidence_ready_for_diagnostics_fix",
        "accepted_evidence_ready_for_player_safe_error_fix",
        "accepted_evidence_ready_for_endurance_fix",
        "accepted_evidence_ready_for_checkpoint_replay_fix",
        "phase12_1_implementation_allowed",
        "phase12_1_implementation_blocked",
    ):
        assert expected in plan


def test_phase12_1_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_1_no_accepted_evidence`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_1_implementation_blocked`",
        "selected fix target: none",
        "documentation and deterministic source guards only",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "package building in CI",
        "runtime implementation without accepted evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "implementation remains blocked without accepted evidence",
    ):
        assert expected in plan
