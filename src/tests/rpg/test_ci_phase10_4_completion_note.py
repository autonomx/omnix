from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_4_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_4_player_safe_error_handling_evidence_envelope.md"


def test_phase10_4_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.4 player-safe error handling evidence envelope is complete.",
        "Implementation PR: #321",
        "a0c5c9c2792a93ecd39fc2137237a86e7ad321b1",
        "39c3e78a78417f2cc3cd48ca4cf8db32c9c7a06d",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_4_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free player-safe error handling evidence envelope",
        "classifies the current state as `player_safe_error_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_4_completion_note_matches_player_safe_error_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "startup_error_evidence",
        "configuration_error_evidence",
        "provider_error_evidence",
        "save_load_error_evidence",
        "persistence_error_evidence",
        "network_error_evidence",
        "resource_error_evidence",
        "unknown_error_evidence",
        "safe_message_evidence",
        "recovery_action_evidence",
        "diagnostic_reference_evidence",
        "internal_detail_separation_evidence",
        "support_bundle_evidence",
        "player_safe_error_evidence_gap",
        "player_safe_error_ready",
    ):
        assert expected in plan
    for expected in (
        "startup",
        "configuration",
        "provider",
        "save/load",
        "persistence",
        "network",
        "resource",
        "unknown",
        "safe message",
        "recovery action",
        "diagnostic reference",
        "internal detail separation",
        "support bundle",
        "player_safe_error_evidence_gap",
        "player_safe_error_ready",
    ):
        assert expected in note
