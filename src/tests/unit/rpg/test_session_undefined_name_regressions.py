from __future__ import annotations

import builtins
from datetime import datetime, timezone

from app.apps.rpg.narration.ai.npc_initiative import build_npc_initiative_candidates
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


def test_npc_initiative_does_not_depend_on_startup_opening_bonus(monkeypatch) -> None:
    monkeypatch.delattr(builtins, "opening_bonus", raising=False)
    simulation_state = {
        "tick": 1,
        "player_state": {"location_id": "market"},
        "npc_index": {
            "npc:ally": {"name": "Ally", "role": "companion", "location_id": "market"}
        },
        "npc_minds": {"npc:ally": {"beliefs": {}, "goals": []}},
    }

    candidates = build_npc_initiative_candidates(
        simulation_state,
        {},
        {"nearby_npc_ids": ["npc:ally"], "player_idle": True},
    )

    assert any(candidate.get("reason") == "companion_idle_presence" for candidate in candidates)
