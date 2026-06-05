from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_7_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_7_live_provider_1000_turn_evidence_runbook.md"


def test_phase11_7_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.7 live/provider 1000-turn evidence capture runbook is complete.",
        "Implementation PR: #341",
        "0d594deb46a5e4eb8f3fbd077d309afda9c5b459",
        "70d10433f38d9549a4422fd2091404d041f85b2c",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_7_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator runbook",
        "live_provider_1000_turn_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_7_completion_note_matches_runbook_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "live_provider_1000_turn_not_started",
        "provider_configuration_gap",
        "model_configuration_gap",
        "run_command_gap",
        "artifact_bundle_gap",
        "checkpoint_artifact_gap",
        "replay_artifact_gap",
        "timing_metrics_gap",
        "hardening_handoff_gap",
        "live_provider_1000_turn_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "provider configuration",
        "model configuration",
        "run command",
        "autoplay summary/transcript/ZIP capture",
        "checkpoint artifact capture",
        "replay artifact capture",
        "hardening handoff",
        "Phase 11.8 — first checkpoint/replay evidence capture runbook",
    ):
        assert expected in note
