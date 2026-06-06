from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_4_player_safe_error_redaction_evidence_decision.md"


def test_phase12_4_core_sections_and_scope():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.4 is the player-safe error/redaction evidence capture or hardening slice",
        "source/test/documentation only",
        "accepted player-safe error/redaction evidence",
        "player-safe error/redaction evidence decision state",
        "implementation-allowed conditions",
        "implementation-blocked conditions",
        "no-evidence baseline",
        "Phase 12.5 — live/provider endurance evidence capture or hardening",
    ):
        assert expected in plan


def test_phase12_4_accepted_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_player_safe_error_evidence_source_path",
        "source_checkout",
        "error_scenario_inventory",
        "startup_error_capture",
        "configuration_error_capture",
        "provider_error_capture",
        "save_load_error_capture",
        "persistence_error_capture",
        "network_error_capture",
        "resource_error_capture",
        "unknown_error_capture",
        "player_message_capture",
        "recovery_action_capture",
        "support_reference_capture",
        "internal_diagnostic_capture",
        "evidence_bundle_manifest",
        "failure_category",
        "reproduction_command_or_steps",
        "affected_component",
        "player_or_operator_impact",
        "deterministic_runtime_boundary_impact",
        "proposed_bounded_fix_target",
        "explicit_non_targets",
        "acceptance_criteria",
        "required_verification_checks",
        "redaction_review",
    ):
        assert expected in plan


def test_phase12_4_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_4_player_safe_error_evidence_not_started",
        "operator_evidence_backfill_required",
        "player_safe_error_evidence_incomplete",
        "error_scenario_inventory_gap",
        "startup_error_capture_gap",
        "configuration_error_capture_gap",
        "provider_error_capture_gap",
        "save_load_error_capture_gap",
        "persistence_error_capture_gap",
        "network_error_capture_gap",
        "resource_error_capture_gap",
        "unknown_error_capture_gap",
        "player_message_capture_gap",
        "recovery_action_capture_gap",
        "support_reference_capture_gap",
        "internal_diagnostic_capture_gap",
        "player_facing_secret_leak_gap",
        "shareable_artifact_redaction_gap",
        "evidence_bundle_gap",
        "player_safe_error_target_ready",
        "phase12_4_implementation_allowed",
        "phase12_4_implementation_blocked",
    ):
        assert expected in plan


def test_phase12_4_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_4_player_safe_error_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_4_implementation_blocked`",
        "selected player-safe error/redaction fix target: none",
        "documentation and deterministic source guards only",
        "player-safe error implementation",
        "redaction implementation",
        "diagnostic separation changes",
        "support-reference changes",
        "recovery-action changes",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "package building in CI",
        "player-safe error/redaction implementation without accepted evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "implementation remains blocked without accepted evidence",
    ):
        assert expected in plan
