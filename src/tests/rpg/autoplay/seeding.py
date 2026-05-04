from __future__ import annotations

from typing import Any, Dict

from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc


def seed_tavern_story_campaign(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Small deterministic seed for first autoplay runs.

    This is intentionally simple: it gives the player-agent an objective, a
    nearby NPC, and a tavern location, without hidden state leaks.
    """
    simulation_state.setdefault("scene", {})
    simulation_state["scene"].update(
        {
            "scene_id": "scene:rusty_flagon",
            "location": "The Rusty Flagon Tavern",
            "description": "A busy medieval tavern with travelers, locals, and a wary innkeeper.",
            "nearby_npcs": [
                {
                    "npc_id": "npc:bran",
                    "name": "Bran",
                    "role": "innkeeper",
                }
            ],
        }
    )
    start_story_arc(
        simulation_state,
        "arc:witness_search",
        title="Witness Search",
        stage="rumors",
        pressure=20,
    )
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:witness_search",
        milestone_id="milestone:find_witness",
        title="Find the witness",
        objective_text="Find the witness near the tavern.",
        quest_id="quest:witness_search",
        priority=80,
        turn_index=0,
    )
    return {
        "ok": True,
        "seed": "tavern_story_seed",
        "scene_id": "scene:rusty_flagon",
        "arc_id": "arc:witness_search",
        "objective_id": "milestone:find_witness",
    }


def seed_campaign(simulation_state: Dict[str, Any], seed_name: str) -> Dict[str, Any]:
    seed_name = str(seed_name or "tavern_story_seed")
    if seed_name in {"", "none"}:
        return {"ok": True, "seed": "none"}
    if seed_name == "tavern_story_seed":
        return seed_tavern_story_campaign(simulation_state)
    raise ValueError(f"unknown_autoplay_seed:{seed_name}")