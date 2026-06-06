from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase12_6_checkpoint_replay_evidence_decision.md"


def test_phase12_6_core_sections_and_scope():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.6 is the checkpoint/replay evidence capture or hardening slice",
        "source/test/documentation only",
        "accepted checkpoint/replay evidence",
        "Phase 12.7 — accepted evidence intake closeout or implementation handoff",
    ):
        assert expected in plan


def test_phase12_6_accepted_evidence_requirements_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "accepted_checkpoint_replay_evidence_source_path",
        "source_checkout",
        "checkpoint_capture_context",
        "checkpoint_artifact_manifest",
        "save_load_roundtrip_reference",
        "replay_command",
        "replay_result",
        "package_disk_replay_reference",
        "determinism_notes",
        "artifact_integrity_notes",
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


def test_phase12_6_decision_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "phase12_6_checkpoint_replay_evidence_not_started",
        "operator_evidence_backfill_required",
        "checkpoint_replay_evidence_incomplete",
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
        "checkpoint_replay_target_ready",
        "phase12_6_implementation_allowed",
        "phase12_6_implementation_blocked",
    ):
        assert expected in plan


def test_phase12_6_no_evidence_boundary_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_6_checkpoint_replay_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_6_implementation_blocked`",
        "selected checkpoint/replay fix target: none",
        "documentation and deterministic source guards only",
        "checkpoint implementation",
        "replay implementation",
        "save/load behavior changes",
        "package/disk replay behavior changes",
        "determinism behavior changes",
        "artifact-integrity behavior changes",
        "runtime behavior changes",
        "gameplay mutation",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "package building in CI",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "checkpoint/replay implementation remains blocked without accepted evidence",
    ):
        assert expected in plan
