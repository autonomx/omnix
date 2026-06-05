from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_8_checkpoint_replay_evidence_runbook.md"


def test_phase11_8_runbook_core_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.8 defines the operator runbook",
        "source/test/documentation only",
        "operator_context",
        "source_checkout",
        "checkpoint_capture_context",
        "checkpoint_artifact_manifest",
        "save_load_roundtrip_reference",
        "replay_command",
        "replay_result",
        "package_disk_replay_reference",
        "determinism_notes",
        "artifact_integrity_notes",
        "failure_classification",
        "hardening_handoff",
        "redaction_review",
        "checkpoint_replay_classification",
        "Phase 11.9 — first hardening target selection from attached evidence",
    ):
        assert expected in plan


def test_phase11_8_artifacts_and_metadata_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "checkpoint artifact directory",
        "checkpoint artifact manifest",
        "save/load roundtrip transcript or reference",
        "replay command transcript",
        "replay result artifact",
        "package/disk replay reference",
        "determinism notes",
        "artifact integrity notes",
        "git SHA and branch",
        "checkpoint source run and turn range",
        "checkpoint interval if captured",
        "replay command and arguments",
        "replay exit status",
        "replay comparison result",
        "determinism status",
    ):
        assert expected in plan


def test_phase11_8_gap_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "checkpoint_replay_capture_not_started",
        "checkpoint_context_gap",
        "checkpoint_artifact_manifest_gap",
        "save_load_roundtrip_reference_gap",
        "replay_command_gap",
        "replay_result_gap",
        "package_disk_replay_reference_gap",
        "determinism_notes_gap",
        "artifact_integrity_gap",
        "failure_classification_gap",
        "hardening_handoff_gap",
        "redaction_review_gap",
        "checkpoint_replay_ready_for_triage",
    ):
        assert expected in plan


def test_phase11_8_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `checkpoint_replay_capture_not_started`",
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
