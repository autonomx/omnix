from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_6_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_6_live_provider_100_turn_evidence_runbook.md"


def test_phase11_6_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.6 live/provider 100-turn evidence capture runbook is complete.",
        "Implementation PR: #339",
        "c32d90f116a09a857486223a0e8554177d5aec1c",
        "4ff39ee4e6e9166c6e105afc726dca3fa08b7d5a",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_6_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator runbook",
        "live_provider_100_turn_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_6_completion_note_matches_runbook_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "live_provider_100_turn_not_started",
        "provider_configuration_gap",
        "model_configuration_gap",
        "run_command_gap",
        "artifact_bundle_gap",
        "autoplay_summary_gap",
        "autoplay_transcript_gap",
        "autoplay_zip_gap",
        "timing_metrics_gap",
        "final_drain_gap",
        "background_job_gap",
        "live_provider_100_turn_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "provider configuration",
        "model configuration",
        "run command",
        "autoplay summary/transcript/ZIP capture",
        "timing metrics",
        "final drain behavior",
        "background job behavior",
        "Phase 11.7 — first live/provider 1000-turn evidence capture runbook",
    ):
        assert expected in note
