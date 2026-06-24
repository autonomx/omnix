from __future__ import annotations

from app.rpg.narration_prompt_runtime import build_narration_prompt_runtime_metadata, prompt_task_for_action
from app.rpg.runtime_phase18_report import build_phase18_turn_report


def _state() -> dict[str, object]:
    return {
        "world": {},
        "player": {},
        "party": {},
        "npcs": {},
        "quests": {},
        "map": {},
        "inventory": {},
        "combat": {},
        "memory": {},
        "seed": 7,
        "counters": {"rng": 1},
        "director_state": {"arcs": [{"arc_id": "trail", "title": "Trail", "threat": "bandits"}]},
    }


def test_prompt_task_for_action_routes_dialogue_and_default() -> None:
    assert prompt_task_for_action("talk") == "npc_dialogue"
    assert prompt_task_for_action("journal") == "journal_recap"
    assert prompt_task_for_action("look") == "narration"


def test_metadata_is_report_only() -> None:
    payload = build_narration_prompt_runtime_metadata(narration="Rain taps the roof.", action_kind="talk")

    assert payload["narration_task"] == "npc_dialogue"
    assert payload["state_mutation_allowed"] is False
    assert payload["provider_dispatch_ready"] is True


def test_phase18_report_wrapper_adds_runtime_metadata() -> None:
    report = build_phase18_turn_report(
        {
            "narration": "Rain taps the roof.",
            "simulation_state": _state(),
            "action_kind": "look",
            "valid_actions": ["look"],
        },
        turn_index=1,
        player_action="look",
        recent_narrations=["Rain taps the roof."],
    )

    runtime = report["phase18_runtime"]
    assert runtime["rewrite_recommended"] is True
    assert runtime["state_mutation_allowed"] is False
