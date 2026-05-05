from __future__ import annotations

from typing import Any, Dict

from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc
from tests.rpg.autoplay.story_hooks import seed_witness_resolution_hooks


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
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:witness_search",
        milestone_id="milestone:report_findings_to_bran",
        title="Report findings to Bran",
        objective_text="Report the witness findings to Bran.",
        quest_id="quest:witness_search",
        priority=70,
        turn_index=0,
    )
    hook_result = seed_witness_resolution_hooks(simulation_state)
    simulation_state.setdefault("npc_profile_state", {}).setdefault("profiles", {}).update(
        {
            "npc:Bran": {
                "npc_id": "npc:Bran",
                "name": "Bran",
                "role": "Innkeeper",
                "history": "Bran runs the Rusty Flagon and hears more rumors than he admits.",
                "biography": "A practical tavern keeper with a protective streak toward his patrons and business.",
                "growth": "Begins cautious and guarded; becomes more invested when the witness report points toward bandits.",
            },
            "npc:Mira": {
                "npc_id": "npc:Mira",
                "name": "Mira",
                "role": "Server",
                "history": "Mira works the tavern floor and notices small details in the room's movement.",
                "biography": "Observant, quick-moving, and used to reading trouble before it reaches the tables.",
                "growth": "Starts as background staff but becomes a useful observer when the investigation focuses on the tavern exit.",
            },
            "npc:CloakedTraveler": {
                "npc_id": "npc:CloakedTraveler",
                "name": "Cloaked Traveler",
                "role": "Witness",
                "history": "A traveler who saw signs of the trouble but tried to avoid being pulled into it.",
                "biography": "Wary, road-worn, and reluctant to speak unless approached through grounded investigation.",
                "growth": "Moves from hidden lead to active witness once the player follows the trail.",
            },
        }
    )
    simulation_state.setdefault("lore_state", {}).setdefault("entries", []).extend(
        [
            {
                "id": "lore:rusty_flagon",
                "title": "The Rusty Flagon Tavern",
                "text": "A busy roadside tavern where rumors, paid information, and trouble often cross paths.",
            },
            {
                "id": "lore:bandit_road",
                "title": "The Bandit Road",
                "text": "A road outside town associated with disappearances, ambushes, and travelers who prefer silence.",
            },
        ]
    )
    simulation_state.setdefault("campaign_director_state", {}).update(
        {
            "campaign_title": "Witness at the Rusty Flagon",
            "premise": (
                "The player begins in the Rusty Flagon Tavern after rumors of a witness, "
                "a hurried traveler, and possible bandit activity begin to converge."
            ),
            "dramatic_question": (
                "Can the player turn tavern rumors into a reliable lead before the trail goes cold?"
            ),
            "opening_tension": (
                "Bran is worried because trouble on the road threatens his patrons, his tavern, "
                "and the fragile trust of travelers passing through."
            ),
            "director_goals": [
                "Introduce Bran and the tavern as a social investigation hub.",
                "Reveal a witness lead through grounded player action.",
                "Branch the story from witness investigation toward the bandit road.",
            ],
            "stakes": [
                "The witness may disappear.",
                "The tavern may become a target if Bran helps too openly.",
                "The bandit trail may point to a wider threat outside town.",
            ],
        }
    )
    simulation_state.setdefault("player_state", {}).update(
        {
            "character_id": "player",
            "name": "The Player",
            "level": 1,
            "experience": 0,
            "experience_to_next_level": 100,
            "stats": {
                "strength": 10,
                "dexterity": 10,
                "constitution": 10,
                "intelligence": 11,
                "wisdom": 12,
                "charisma": 10,
            },
            "progression_log": [
                {
                    "turn_index": 0,
                    "type": "campaign_start",
                    "summary": "The player begins as a level 1 adventurer investigating rumors at the Rusty Flagon.",
                }
            ],
        }
    )
    simulation_state.setdefault("npc_progression_state", {}).setdefault("npcs", {}).update(
        {
            "Bran": {
                "name": "Bran",
                "level": 1,
                "disposition": "guarded",
                "trust": 0,
                "growth_stage": "cautious_innkeeper",
                "progression_log": [
                    {
                        "turn_index": 0,
                        "summary": "Bran begins guarded, worried about rumors but reluctant to expose himself or his tavern.",
                    }
                ],
            },
            "Mira": {
                "name": "Mira",
                "level": 1,
                "disposition": "observant",
                "trust": 0,
                "growth_stage": "background_observer",
                "progression_log": [
                    {
                        "turn_index": 0,
                        "summary": "Mira begins as an observant tavern worker who notices details others miss.",
                    }
                ],
            },
            "Cloaked Traveler": {
                "name": "Cloaked Traveler",
                "level": 1,
                "disposition": "wary",
                "trust": 0,
                "growth_stage": "hidden_witness",
                "progression_log": [
                    {
                        "turn_index": 0,
                        "summary": "The cloaked traveler begins as a hidden witness trying not to become involved.",
                    }
                ],
            },
        }
    )
    return {
        "ok": True,
        "seed": "tavern_story_seed",
        "scene_id": "scene:rusty_flagon",
        "arc_id": "arc:witness_search",
        "objective_id": "milestone:find_witness",
        "story_hooks": hook_result,
    }


def seed_campaign(simulation_state: Dict[str, Any], seed_name: str) -> Dict[str, Any]:
    seed_name = str(seed_name or "tavern_story_seed")
    if seed_name in {"", "none"}:
        return {"ok": True, "seed": "none"}
    if seed_name == "tavern_story_seed":
        return seed_tavern_story_campaign(simulation_state)
    raise ValueError(f"unknown_autoplay_seed:{seed_name}")