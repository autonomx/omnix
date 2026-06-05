from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_2_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_2_operator_evidence_backfill_plan.md"


def test_phase11_2_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.2 operator evidence backfill plan is complete.",
        "Implementation PR: #331",
        "561f79445b8e39b0ad966514c52e0ee816a369ec",
        "7ae0c7565f9ecd90a1909014ad45afa15cae429f",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_2_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator evidence backfill plan",
        "operator_backfill_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_2_completion_note_matches_backfill_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "operator_backfill_not_started",
        "package_artifact_backfill_gap",
        "install_run_backfill_gap",
        "configuration_backfill_gap",
        "persistence_backfill_gap",
        "diagnostic_backfill_gap",
        "player_safe_error_backfill_gap",
        "live_1000_turn_backfill_gap",
        "concrete_hardening_target_found",
        "operator_backfill_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "package artifact inventory",
        "install/run transcript",
        "configuration snapshot",
        "persistence smoke artifacts",
        "diagnostic bundle artifacts",
        "player-safe error artifacts",
        "live/provider 1000-turn evidence",
        "Phase 11.3 — operator runbook for first package/install/run evidence capture",
    ):
        assert expected in note
