from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_5_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_5_player_safe_error_redaction_evidence_runbook.md"


def test_phase11_5_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.5 player-safe error and redaction evidence capture runbook is complete.",
        "Implementation PR: #337",
        "2359bad256787b0fba73fdb1571a12be86c69048",
        "eed911801166bdb7c1f2876d1e02bc6afe6f69d7",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_5_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator runbook",
        "player_safe_error_capture_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_5_completion_note_matches_runbook_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "player_safe_error_capture_not_started",
        "error_scenario_inventory_gap",
        "startup_error_capture_gap",
        "configuration_error_capture_gap",
        "provider_error_capture_gap",
        "player_message_capture_gap",
        "recovery_action_capture_gap",
        "support_reference_capture_gap",
        "player_facing_secret_leak_gap",
        "player_safe_error_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "error scenario inventory",
        "player message capture",
        "recovery action capture",
        "support reference capture",
        "internal diagnostic capture",
        "redaction review",
        "Phase 11.6 — first live/provider 100-turn evidence capture runbook",
    ):
        assert expected in note
