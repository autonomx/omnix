from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_2_package_install_run_evidence_decision.md"


def test_phase12_2_core_sections_and_scope():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.2 is the package/install/run evidence capture or hardening slice",
        "source/test/documentation only",
        "accepted package/install/run evidence",
        "package/install/run evidence decision state",
        "implementation-allowed conditions",
        "implementation-blocked conditions",
        "no-evidence baseline",
        "Phase 12.3 — persistence/diagnostics evidence capture or hardening",
    ):
        assert expected in plan


def test_phase12_2_accepted_package_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_package_evidence_source_path",
        "source_checkout",
        "package_artifact_inventory",
        "package_checksum_or_checkout_reference",
        "dependency_install_transcript",
        "configuration_snapshot",
        "environment_variable_snapshot",
        "resource_path_snapshot",
        "data_path_snapshot",
        "launch_command_transcript",
        "startup_health_check",
        "runtime_smoke_transcript",
        "shutdown_transcript",
        "diagnostic_collection_reference",
        "failure_category",
        "reproduction_command_or_steps",
        "affected_component",
        "operator_impact",
        "deterministic_runtime_boundary_impact",
        "proposed_bounded_fix_target",
        "explicit_non_targets",
        "acceptance_criteria",
        "required_verification_checks",
        "redaction_review",
    ):
        assert expected in plan


def test_phase12_2_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_2_package_evidence_not_started",
        "operator_evidence_backfill_required",
        "package_evidence_incomplete",
        "package_artifact_gap",
        "install_transcript_gap",
        "configuration_snapshot_gap",
        "environment_snapshot_gap",
        "resource_path_snapshot_gap",
        "data_path_snapshot_gap",
        "launch_transcript_gap",
        "startup_health_gap",
        "runtime_smoke_gap",
        "shutdown_transcript_gap",
        "diagnostic_collection_gap",
        "redaction_review_gap",
        "package_install_run_target_ready",
        "phase12_2_implementation_allowed",
        "phase12_2_implementation_blocked",
    ):
        assert expected in plan


def test_phase12_2_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_2_package_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_2_implementation_blocked`",
        "selected package/install/run fix target: none",
        "documentation and deterministic source guards only",
        "package implementation",
        "installer changes",
        "launch behavior changes",
        "configuration behavior changes",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "package building in CI",
        "package/install/run implementation without accepted evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "implementation remains blocked without accepted package evidence",
    ):
        assert expected in plan
