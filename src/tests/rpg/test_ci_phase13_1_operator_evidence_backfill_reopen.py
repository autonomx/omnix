from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase13_1_operator_evidence_backfill_reopen.md"


def test_phase13_1_core_sections_and_evidence_categories():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 13.1 reopens operator evidence backfill unless accepted evidence is attached",
        "source/test/documentation only",
        "package_install_run_evidence",
        "persistence_diagnostics_evidence",
        "player_safe_error_redaction_evidence",
        "live_provider_100_turn_evidence",
        "live_provider_1000_turn_evidence",
        "checkpoint_replay_evidence",
        "ci_failure_logs",
        "source_backed_diagnostics",
    ):
        assert expected in plan


def test_phase13_1_accepted_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_evidence_source_path",
        "accepted_evidence_category",
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
        "phase13_recommended_implementation_slice",
    ):
        assert expected in plan


def test_phase13_1_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase13_1_no_accepted_evidence",
        "operator_evidence_backfill_reopened",
        "accepted_evidence_incomplete",
        "accepted_evidence_selects_single_target",
        "phase13_implementation_allowed",
        "phase13_implementation_blocked",
    ):
        assert expected in plan


def test_phase13_1_no_evidence_boundary_and_testing_packet():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase13_1_no_accepted_evidence`",
        "secondary classification: `operator_evidence_backfill_reopened`",
        "implementation state: `phase13_implementation_blocked`",
        "selected implementation target: none",
        "documentation and deterministic source guards only",
        "package checkout, install, launch, startup, smoke, and shutdown transcripts",
        "save/load roundtrip and checkpoint/replay artifacts",
        "diagnostic logs and diagnostic bundle manifests",
        "100-turn and 1000-turn live/provider endurance artifacts",
        "provider calls",
        "LLM calls",
        "live 100-turn or 1000-turn CI execution",
        "package building in CI",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "Phase 13 implementation remains blocked without accepted evidence",
    ):
        assert expected in plan
