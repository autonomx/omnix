from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_3_persistence_diagnostics_evidence_decision.md"


def test_phase12_3_core_sections_and_scope():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.3 is the persistence/diagnostics evidence capture or hardening slice",
        "source/test/documentation only",
        "accepted persistence/diagnostics evidence",
        "persistence/diagnostics evidence decision state",
        "implementation-allowed conditions",
        "implementation-blocked conditions",
        "no-evidence baseline",
        "Phase 12.4 — player-safe error/redaction evidence capture or hardening",
    ):
        assert expected in plan


def test_phase12_3_accepted_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_persistence_diagnostics_evidence_source_path",
        "source_checkout",
        "save_path_snapshot",
        "session_path_snapshot",
        "data_path_snapshot",
        "report_path_snapshot",
        "save_load_roundtrip_steps",
        "save_load_roundtrip_result",
        "saved_state_artifact_reference",
        "replay_artifact_capture",
        "package_disk_artifact_capture",
        "diagnostic_log_capture",
        "diagnostic_bundle_manifest",
        "failure_reproduction_steps",
        "failure_category",
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


def test_phase12_3_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_3_persistence_diagnostics_evidence_not_started",
        "operator_evidence_backfill_required",
        "persistence_diagnostics_evidence_incomplete",
        "save_path_capture_gap",
        "session_path_capture_gap",
        "data_path_capture_gap",
        "report_path_capture_gap",
        "save_load_roundtrip_capture_gap",
        "saved_state_artifact_gap",
        "replay_artifact_capture_gap",
        "package_disk_artifact_capture_gap",
        "diagnostic_log_capture_gap",
        "diagnostic_bundle_capture_gap",
        "failure_reproduction_gap",
        "redaction_review_gap",
        "persistence_diagnostics_target_ready",
        "phase12_3_implementation_allowed",
        "phase12_3_implementation_blocked",
    ):
        assert expected in plan


def test_phase12_3_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_3_persistence_diagnostics_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_3_implementation_blocked`",
        "selected persistence/diagnostics fix target: none",
        "documentation and deterministic source guards only",
        "persistence implementation",
        "diagnostics implementation",
        "save/load behavior changes",
        "replay behavior changes",
        "artifact behavior changes",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "package building in CI",
        "persistence/diagnostics implementation without accepted evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "implementation remains blocked without accepted persistence/diagnostics evidence",
    ):
        assert expected in plan
