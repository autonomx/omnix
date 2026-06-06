from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_5_endurance_evidence_decision.md"


def test_phase12_5_core_sections_and_scope():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.5 is the live-run endurance evidence capture or hardening slice",
        "source/test/documentation only",
        "accepted endurance evidence",
        "Phase 12.6 — checkpoint/replay evidence capture or hardening",
    ):
        assert expected in plan


def test_phase12_5_accepted_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_endurance_evidence_source_path",
        "source_checkout",
        "service_configuration",
        "model_configuration",
        "run_command",
        "runtime_configuration_snapshot",
        "requested_turn_count",
        "turns_executed",
        "run_exit_status",
        "artifact_bundle_manifest",
        "autoplay_summary_capture",
        "autoplay_transcript_capture",
        "autoplay_zip_capture",
        "checkpoint_artifact_capture",
        "replay_artifact_capture",
        "timing_metrics_capture",
        "final_drain_capture",
        "background_job_capture",
        "progress_quality_review",
        "continuity_review",
        "failure_category",
        "hardening_handoff",
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


def test_phase12_5_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_5_endurance_evidence_not_started",
        "operator_evidence_backfill_required",
        "endurance_evidence_incomplete",
        "service_configuration_gap",
        "model_configuration_gap",
        "run_command_gap",
        "runtime_configuration_gap",
        "turn_count_gap",
        "run_exit_status_gap",
        "artifact_bundle_gap",
        "autoplay_summary_gap",
        "autoplay_transcript_gap",
        "autoplay_zip_gap",
        "checkpoint_artifact_gap",
        "replay_artifact_gap",
        "timing_metrics_gap",
        "final_drain_gap",
        "background_job_gap",
        "progress_quality_review_gap",
        "continuity_review_gap",
        "failure_classification_gap",
        "hardening_handoff_gap",
        "redaction_review_gap",
        "endurance_target_ready",
        "phase12_5_implementation_allowed",
        "phase12_5_implementation_blocked",
    ):
        assert expected in plan


def test_phase12_5_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_5_endurance_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_5_implementation_blocked`",
        "selected endurance fix target: none",
        "documentation and deterministic source guards only",
        "endurance implementation",
        "runtime behavior changes",
        "external-service behavior changes",
        "final-drain changes",
        "background-job changes",
        "timing behavior changes",
        "progress-quality changes",
        "continuity changes",
        "checkpoint/replay changes",
        "gameplay mutation",
        "service calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "UI authority changes",
        "package building in CI",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "endurance implementation remains blocked without accepted evidence",
    ):
        assert expected in plan
