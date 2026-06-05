from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_4_persistence_diagnostics_evidence_runbook.md"


def test_phase11_4_runbook_core_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.4 defines the operator runbook",
        "source/test/documentation only",
        "operator_context",
        "source_checkout",
        "save_path_snapshot",
        "session_path_snapshot",
        "data_path_snapshot",
        "report_path_snapshot",
        "save_load_roundtrip_steps",
        "save_load_roundtrip_result",
        "replay_artifact_capture",
        "package_disk_artifact_capture",
        "diagnostic_log_capture",
        "diagnostic_bundle_manifest",
        "failure_reproduction_steps",
        "redaction_review",
        "persistence_diagnostics_classification",
        "Phase 11.5 — first player-safe error and redaction evidence capture runbook",
    ):
        assert expected in plan


def test_phase11_4_artifacts_and_metadata_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "save directory manifest",
        "session directory manifest",
        "data directory manifest",
        "report directory manifest",
        "save/load roundtrip transcript",
        "saved state artifact",
        "replay artifact",
        "package/disk artifact",
        "diagnostic log files",
        "diagnostic bundle archive",
        "failure reproduction note",
        "git SHA and branch",
        "operator name or role",
        "save/session/data/report directory paths",
        "exit status or observed result for roundtrip, replay, and diagnostic collection",
        "secrets, tokens, provider keys, personal data, and sensitive local paths were redacted",
    ):
        assert expected in plan


def test_phase11_4_gap_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "persistence_diagnostics_capture_not_started",
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
        "persistence_diagnostics_ready_for_triage",
    ):
        assert expected in plan


def test_phase11_4_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `persistence_diagnostics_capture_not_started`",
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
