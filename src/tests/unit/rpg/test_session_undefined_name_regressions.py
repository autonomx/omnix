from __future__ import annotations

from datetime import datetime, timezone

from app.apps.rpg.session import action_execution, narration_jobs, player_activity_runtime


def test_unmatched_player_action_returns_empty_action() -> None:
    state = {"tick": 4, "threads": {}, "factions": {}}

    assert action_execution.derive_player_action(state, "I wait by the gate") == {}


def test_ambient_conversation_line_uses_artifact_text_fields() -> None:
    assert narration_jobs._ambient_conversation_artifact_line({"narration": "A quiet reply."}) == (
        "A quiet reply."
    )


def test_activity_elapsed_time_uses_injected_runtime_clock(monkeypatch) -> None:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(player_activity_runtime, "utc_now", lambda: now)

    assert player_activity_runtime._seconds_since_iso("2026-09-30T11:59:30+00:00") == 30
