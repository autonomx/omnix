from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_2_operator_evidence_backfill_plan.md"


def test_phase11_2_backfill_core_terms():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.2 defines the operator evidence backfill plan",
        "source/test/documentation only",
        "operator_evidence_backfill_required",
        "package_artifact_inventory",
        "install_run_transcript",
        "configuration_snapshot",
        "persistence_smoke_artifacts",
        "diagnostic_bundle_artifacts",
        "player_safe_error_artifacts",
        "release_candidate_artifacts",
        "live_provider_100_turn_evidence",
        "live_provider_1000_turn_evidence",
        "timing_drain_resource_evidence",
        "Phase 11.3 — operator runbook for first package/install/run evidence capture",
    ):
        assert expected in plan


def test_phase11_2_required_fields_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "evidence category",
        "operator command or collection steps",
        "expected artifact paths",
        "required metadata fields",
        "redaction requirements",
        "acceptance criteria",
        "gap classification if missing",
        "next action when evidence is missing",
        "next action when evidence identifies a concrete failure",
    ):
        assert expected in plan


def test_phase11_2_gap_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "operator_backfill_not_started",
        "package_artifact_backfill_gap",
        "install_run_backfill_gap",
        "configuration_backfill_gap",
        "persistence_backfill_gap",
        "diagnostic_backfill_gap",
        "player_safe_error_backfill_gap",
        "release_candidate_backfill_gap",
        "redaction_review_backfill_gap",
        "operator_signoff_backfill_gap",
        "live_100_turn_backfill_gap",
        "live_1000_turn_backfill_gap",
        "checkpoint_backfill_gap",
        "progress_quality_review_gap",
        "continuity_review_gap",
        "timing_resource_backfill_gap",
        "concrete_hardening_target_found",
        "operator_backfill_ready_for_triage",
    ):
        assert expected in plan


def test_phase11_2_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `operator_backfill_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "documentation and deterministic source guards only",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "speculative hardening without concrete evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
