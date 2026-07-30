from __future__ import annotations

from app.assist_core.hermes_rpg_context import hermes_rpg_context_from_session
from app.rpg.session.published_opening_progress import (
    ensure_published_opening_progress,
)


def test_published_opening_recovers_quest_and_grounded_actions() -> None:
    session = {
        "manifest": {"scenario_id": "scenario:black-rain-rising"},
        "state": {
            "current_location_name": "Tidebreak Docks",
            "published_world": {
                "starting_location_id": "ent:places:tidebreak-docks"
            },
            "quests": [],
            "quick_actions": [
                "Survey Tidebreak Docks",
                "Follow the immediate lead",
                "Talk to someone nearby",
                "Check local routes",
            ],
        },
        "campaign_bible_projection": {
            "entities": {
                "ent:opening_scenarios:black-rain-rising": {
                    "id": "ent:opening_scenarios:black-rain-rising",
                    "kind": "opening_scenario",
                    "name": "Black Rain Rising",
                    "premise": "Prevent a flood disaster.",
                    "starting_place_id": "ent:places:tidebreak-docks",
                    "beats": ["Strike confrontation", "Container discovery"],
                    "initial_actor_ids": ["ent:actors:juno-rask"],
                },
                "ent:actors:juno-rask": {
                    "id": "ent:actors:juno-rask",
                    "kind": "npc",
                    "name": "Juno Rask",
                },
            }
        },
        "simulation_state": {},
        "runtime_state": {},
    }

    recovered = ensure_published_opening_progress(session)
    quest = recovered["state"]["quests"][0]

    assert quest["title"] == "Black Rain Rising"
    assert quest["next_step"] == "Strike confrontation"
    assert recovered["state"]["quick_actions"][0]["label"] == (
        "Strike confrontation"
    )
    assert recovered["simulation_state"]["quest_state"]["quests"][0] == quest

    context = hermes_rpg_context_from_session("session:vesper", recovered)
    assert context["context"]["objectives"] == ["Strike confrontation"]
