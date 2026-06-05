from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_7_live_provider_1000_turn_evidence_runbook.md"


def test_phase11_7_runbook_core_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.7 defines the operator runbook",
        "source/test/documentation only",
        "operator_context",
        "source_checkout",
        "provider_configuration",
        "model_configuration",
        "run_command",
        "runtime_configuration_snapshot",
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
        "failure_classification",
        "hardening_handoff",
        "redaction_review",
        "live_provider_1000_turn_classification",
        "Phase 11.8 — first checkpoint/replay evidence capture runbook",
    ):
        assert expected in plan


def test_phase11_7_artifacts_and_metadata_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "operator command transcript",
        "provider/model/config snapshot",
        "`autoplay-summary.json`",
        "`autoplay-transcript.json`",
        "`autoplay-campaign-results.zip`",
        "checkpoint artifact paths",
        "replay artifact paths",
        "timing metrics summary",
        "final drain notes",
        "background job notes",
        "progress-quality review note",
        "continuity review note",
        "git SHA and branch",
        "provider name",
        "model name",
        "exact run command",
        "requested turn count",
        "turns executed",
        "wall-clock time",
        "checkpoint interval and artifact paths if captured",
        "replay verification result if captured",
    ):
        assert expected in plan


def test_phase11_7_gap_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "live_provider_1000_turn_not_started",
        "provider_configuration_gap",
        "model_configuration_gap",
        "run_command_gap",
        "runtime_configuration_gap",
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
        "live_provider_1000_turn_ready_for_triage",
    ):
        assert expected in plan


def test_phase11_7_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `live_provider_1000_turn_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "documentation and deterministic source guards only",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "package building in CI",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
