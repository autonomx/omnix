from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_5_player_safe_error_redaction_evidence_runbook.md"


def test_phase11_5_runbook_core_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.5 defines the operator runbook",
        "source/test/documentation only",
        "operator_context",
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
        "redaction_review",
        "evidence_bundle_manifest",
        "player_safe_error_classification",
        "Phase 11.6 — first live/provider 100-turn evidence capture runbook",
    ):
        assert expected in plan


def test_phase11_5_artifacts_and_metadata_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "error scenario inventory",
        "player-facing message transcript or screenshot notes",
        "recovery action transcript or screenshot notes",
        "support reference transcript or screenshot notes",
        "internal diagnostic log files",
        "diagnostic bundle archive",
        "redaction review note",
        "shareable evidence bundle archive",
        "git SHA and branch",
        "operator name or role",
        "error scenario category",
        "player-facing text observed",
        "recovery action observed",
        "support reference or correlation identifier observed",
        "internal diagnostic artifact paths",
        "raw stack traces",
        "sensitive local paths were redacted from shareable artifacts",
    ):
        assert expected in plan


def test_phase11_5_gap_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "player_safe_error_capture_not_started",
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
        "player_safe_error_ready_for_triage",
    ):
        assert expected in plan


def test_phase11_5_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `player_safe_error_capture_not_started`",
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
