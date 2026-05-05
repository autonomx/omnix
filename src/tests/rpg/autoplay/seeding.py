from __future__ import annotations

import random
from typing import Any, Dict

from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc
from tests.rpg.autoplay.story_hooks import seed_witness_resolution_hooks

DEFAULT_CAMPAIGN_SEED = "tavern_story_seed"


CAMPAIGN_SEED_NAMES = [
    "tavern_story_seed",
    "caravan_ambush_seed",
    "missing_apprentice_seed",
    "haunted_mill_seed",
    "noble_blackmail_seed",
]


def available_campaign_seeds() -> list[str]:
    return list(CAMPAIGN_SEED_NAMES)


def resolve_campaign_seed_name(
    requested_seed: str,
    *,
    random_seed: int | None = None,
) -> Dict[str, Any]:
    requested = (requested_seed or DEFAULT_CAMPAIGN_SEED).strip()
    if requested == "random":
        rng = random.Random(random_seed)
        resolved = rng.choice(CAMPAIGN_SEED_NAMES)
        return {
            "requested_seed": requested,
            "resolved_seed": resolved,
            "random_seed": random_seed,
            "available_seeds": available_campaign_seeds(),
            "randomized": True,
        }
    if requested not in CAMPAIGN_SEED_NAMES:
        raise ValueError(
            f"unknown_campaign_seed:{requested}; available={','.join(CAMPAIGN_SEED_NAMES)}"
        )
    return {
        "requested_seed": requested,
        "resolved_seed": requested,
        "random_seed": random_seed,
        "available_seeds": available_campaign_seeds(),
        "randomized": False,
    }


def _reset_seed_roots(simulation_state: Dict[str, Any]) -> None:
    for key in [
        "campaign_director_state",
        "campaign_journal_state",
        "inventory_state",
        "lore_state",
        "npc_profile_state",
        "npc_progression_state",
        "player_state",
        "story_arc_state",
        "story_arc_milestone_state",
        "story_event_queue_state",
        "autoplay_story_hook_state",
    ]:
        simulation_state.pop(key, None)


def _seed_common_player(
    simulation_state: Dict[str, Any],
    *,
    gold: int = 15,
    silver: int = 8,
) -> None:
    simulation_state.setdefault("player_state", {}).update(
        {
            "character_id": "player",
            "name": "The Player",
            "level": 1,
            "experience": 0,
            "experience_to_next_level": 100,
            "inventory": {
                "currency": {
                    "gold": gold,
                    "silver": silver,
                },
                "items": [
                    {
                        "item_id": "item:travelers_cloak",
                        "name": "Traveler's Cloak",
                        "quantity": 1,
                        "type": "gear",
                        "description": "A weathered cloak suitable for road travel.",
                    },
                    {
                        "item_id": "item:iron_dagger",
                        "name": "Iron Dagger",
                        "quantity": 1,
                        "type": "weapon",
                        "description": "A simple backup blade.",
                    },
                    {
                        "item_id": "item:rations",
                        "name": "Trail Rations",
                        "quantity": 3,
                        "type": "consumable",
                        "description": "Basic food for short travel.",
                    },
                    {
                        "item_id": "item:waterskin",
                        "name": "Waterskin",
                        "quantity": 1,
                        "type": "gear",
                        "description": "A filled waterskin.",
                    },
                    {
                        "item_id": "item:journal",
                        "name": "Plain Journal",
                        "quantity": 1,
                        "type": "tool",
                        "description": "A small book for notes, rumors, and leads.",
                    },
                ],
            },
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
                    "summary": "The player begins as a level 1 adventurer with basic travel gear.",
                }
            ],
        }
    )
    simulation_state.setdefault("inventory_state", {}).update(
        simulation_state.get("player_state", {}).get("inventory", {})
    )


def _seed_arc(
    simulation_state: Dict[str, Any],
    *,
    arc_id: str,
    title: str,
    stage: str,
    milestones: list[Dict[str, Any]],
    pressure: int = 35,
) -> None:
    simulation_state.setdefault("story_arc_state", {}).setdefault("arcs", {})[arc_id] = {
        "arc_id": arc_id,
        "title": title,
        "stage": stage,
        "status": "active",
        "pressure": pressure,
    }
    simulation_state.setdefault("story_arc_milestone_state", {}).setdefault("arcs", {})[
        arc_id
    ] = {
        "milestones": milestones,
    }


def _seed_initial_journal(
    simulation_state: Dict[str, Any],
    *,
    entry_id: str,
    title: str,
    text: str,
    tags: list[str] | None = None,
) -> None:
    simulation_state.setdefault("campaign_journal_state", {}).setdefault("entries", []).append(
        {
            "entry_id": entry_id,
            "turn_index": 0,
            "title": title,
            "text": text,
            "tags": tags or ["campaign_start"],
        }
    )


def _seed_event(
    simulation_state: Dict[str, Any],
    *,
    event_id: str,
    title: str,
    summary: str,
    severity: str = "medium",
) -> None:
    simulation_state.setdefault("story_event_queue_state", {}).setdefault("queue", []).append(
        {
            "event_id": event_id,
            "turn_index": 0,
            "title": title,
            "summary": summary,
            "severity": severity,
        }
    )


def _seed_npc_profiles(
    simulation_state: Dict[str, Any],
    profiles: Dict[str, Dict[str, Any]],
) -> None:
    simulation_state.setdefault("npc_profile_state", {}).setdefault("profiles", {}).update(profiles)
    progression = simulation_state.setdefault("npc_progression_state", {}).setdefault("npcs", {})
    for profile in profiles.values():
        name = profile.get("name") or profile.get("npc_id") or "Unknown NPC"
        progression.setdefault(
            name,
            {
                "name": name,
                "level": 1,
                "disposition": profile.get("disposition", "neutral"),
                "trust": 0,
                "growth_stage": profile.get("growth_stage", "introduced"),
                "progression_log": [
                    {
                        "turn_index": 0,
                        "summary": profile.get("growth")
                    or profile.get("biography")
                    or f"{name} is introduced to the campaign.",
                    }
                ],
            },
        )


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
    _seed_common_player(simulation_state)
    simulation_state["player_state"]["progression_log"][0][
        "summary"
    ] = "The player begins as a level 1 adventurer investigating rumors at the Rusty Flagon."
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


def seed_caravan_ambush_campaign(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    _reset_seed_roots(simulation_state)
    _seed_common_player(simulation_state, gold=12, silver=5)
    simulation_state["campaign_director_state"] = {
        "campaign_title": "Ash on the Trade Road",
        "premise": "The player reaches a trade road shortly after a merchant caravan is ambushed and left burning near a dry ravine.",
        "dramatic_question": "Can the player identify who attacked the caravan before survivors scatter and evidence is lost?",
        "opening_tension": "Merchants fear the attack was too coordinated to be ordinary banditry.",
        "director_goals": [
            "Introduce a road encounter with immediate stakes.",
            "Offer investigation, rescue, and pursuit paths.",
            "Reveal whether the ambush points to bandits, mercenaries, or an inside betrayal.",
        ],
        "stakes": [
            "Survivors may die without aid.",
            "Trade through the region may collapse.",
            "The attackers may strike the next caravan.",
        ],
    }
    simulation_state["lore_state"] = {
        "entries": [
            {
                "id": "lore:trade_road",
                "title": "The Old Trade Road",
                "text": "A long road connecting market towns, exposed ravines, and isolated caravan stops.",
            },
            {
                "id": "lore:ember_ravine",
                "title": "Ember Ravine",
                "text": "A dry ravine where smoke lingers after the caravan attack and tracks are difficult to read.",
            },
        ]
    }
    _seed_npc_profiles(
        simulation_state,
        {
            "npc:Selka": {
                "npc_id": "npc:Selka",
                "name": "Selka",
                "role": "Caravan Guard",
                "history": "Selka survived the ambush but lost most of her company.",
                "biography": "A disciplined guard trying to hide panic behind procedure.",
                "growth": "Begins defensive and suspicious; may become an ally if survivors are protected.",
                "growth_stage": "wounded_guard",
            },
            "npc:Orren": {
                "npc_id": "npc:Orren",
                "name": "Orren",
                "role": "Merchant Factor",
                "history": "Orren managed the caravan's contracts and knows what cargo mattered most.",
                "biography": "A nervous merchant whose fear may conceal useful details.",
                "growth": "Begins evasive; may reveal the cargo was targeted.",
                "growth_stage": "fearful_merchant",
            },
        },
    )
    _seed_arc(
        simulation_state,
        arc_id="arc:caravan_ambush",
        title="Caravan Ambush",
        stage="aftermath",
        pressure=55,
        milestones=[
            {
                "milestone_id": "milestone:aid_survivors",
                "title": "Aid the survivors",
                "objective_text": "Stabilize survivors and learn what happened during the ambush.",
                "status": "active",
                "priority": 90,
            },
            {
                "milestone_id": "milestone:inspect_wreckage",
                "title": "Inspect the wreckage",
                "objective_text": "Search the burned wagons and ravine for evidence.",
                "status": "active",
                "priority": 80,
            },
            {
                "milestone_id": "milestone:identify_attackers",
                "title": "Identify the attackers",
                "objective_text": "Determine whether the attack was banditry, mercenary work, or betrayal.",
                "status": "active",
                "priority": 70,
            },
        ],
    )
    _seed_initial_journal(
        simulation_state,
        entry_id="journal:caravan_ambush:start",
        title="Smoke on the Trade Road",
        text="A caravan has been ambushed near Ember Ravine. Survivors and evidence remain at risk.",
    )
    _seed_event(
        simulation_state,
        event_id="event:caravan_ambush:aftermath",
        title="Caravan Ambush Aftermath",
        summary="The player arrives after a coordinated attack on a merchant caravan.",
        severity="high",
    )
    return {"ok": True, "seed": "caravan_ambush_seed", "hook_result": {"ok": True}}


def seed_missing_apprentice_campaign(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    _reset_seed_roots(simulation_state)
    _seed_common_player(simulation_state, gold=10, silver=12)
    simulation_state["campaign_director_state"] = {
        "campaign_title": "The Missing Apprentice",
        "premise": "A village apothecary begs for help after an apprentice vanishes while gathering herbs near the old standing stones.",
        "dramatic_question": "Can the player find the apprentice before fear turns the village against the wrong suspect?",
        "opening_tension": "The village is split between superstition, suspicion, and practical urgency.",
        "director_goals": [
            "Introduce a village mystery with social pressure.",
            "Create suspects with partial truths.",
            "Branch toward rescue, accusation, or supernatural investigation.",
        ],
        "stakes": [
            "The apprentice may still be alive.",
            "A false accusation could tear the village apart.",
            "The standing stones may hide a larger danger.",
        ],
    }
    simulation_state["lore_state"] = {
        "entries": [
            {
                "id": "lore:greenhollow",
                "title": "Greenhollow Village",
                "text": "A small herb-growing village where everyone knows each other's secrets.",
            },
            {
                "id": "lore:standing_stones",
                "title": "The Old Standing Stones",
                "text": "Ancient stones outside the village, avoided after sunset and blamed for disappearances.",
            },
        ]
    }
    _seed_npc_profiles(
        simulation_state,
        {
            "npc:Maela": {
                "npc_id": "npc:Maela",
                "name": "Maela",
                "role": "Apothecary",
                "history": "Maela trained the missing apprentice and feels responsible.",
                "biography": "A practical healer fighting panic with work.",
                "growth": "Begins desperate; may become a grounded source of village truth.",
                "growth_stage": "desperate_mentor",
            },
            "npc:Tovin": {
                "npc_id": "npc:Tovin",
                "name": "Tovin",
                "role": "Miller's Son",
                "history": "Tovin argued with the apprentice before the disappearance.",
                "biography": "Defensive, frightened, and hiding something small that looks larger than it is.",
                "growth": "Begins as a suspect; may become a witness.",
                "growth_stage": "suspect",
            },
        },
    )
    _seed_arc(
        simulation_state,
        arc_id="arc:missing_apprentice",
        title="Missing Apprentice",
        stage="village_alarm",
        pressure=45,
        milestones=[
            {
                "milestone_id": "milestone:question_maela",
                "title": "Question Maela",
                "objective_text": "Learn where the apprentice was last seen.",
                "status": "active",
                "priority": 90,
            },
            {
                "milestone_id": "milestone:search_herb_path",
                "title": "Search the herb path",
                "objective_text": "Follow the route toward the standing stones.",
                "status": "active",
                "priority": 80,
            },
            {
                "milestone_id": "milestone:separate_truth_from_rumor",
                "title": "Separate truth from rumor",
                "objective_text": "Resolve which village rumors are backed by evidence.",
                "status": "active",
                "priority": 70,
            },
        ],
    )
    _seed_initial_journal(
        simulation_state,
        entry_id="journal:missing_apprentice:start",
        title="A Vanished Apprentice",
        text="An apprentice disappeared while gathering herbs near the old standing stones.",
    )
    _seed_event(
        simulation_state,
        event_id="event:missing_apprentice:village_alarm",
        title="Village Alarm",
        summary="Greenhollow is frightened after the apprentice vanishes.",
        severity="medium",
    )
    return {"ok": True, "seed": "missing_apprentice_seed", "hook_result": {"ok": True}}


def seed_haunted_mill_campaign(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    _reset_seed_roots(simulation_state)
    _seed_common_player(simulation_state, gold=9, silver=14)
    simulation_state["campaign_director_state"] = {
        "campaign_title": "The Haunted Mill",
        "premise": "A riverside mill has gone silent after three nights of strange lights and impossible knocking from inside the locked wheelhouse.",
        "dramatic_question": "Can the player discover whether the haunting is real, staged, or something worse?",
        "opening_tension": "The mill feeds the town, and every silent day pushes the town closer to panic.",
        "director_goals": [
            "Introduce a gothic investigation location.",
            "Create ambiguity between supernatural and human causes.",
            "Branch toward exorcism, exposure, or rescue.",
        ],
        "stakes": [
            "The town's food supply is threatened.",
            "Fear may turn into violence.",
            "Someone may be trapped or hiding inside the mill.",
        ],
    }
    simulation_state["lore_state"] = {
        "entries": [
            {
                "id": "lore:graywater_mill",
                "title": "Graywater Mill",
                "text": "A river mill whose locked wheelhouse has become the center of local fear.",
            },
            {
                "id": "lore:mill_ghost",
                "title": "The Miller's Ghost",
                "text": "A local legend claiming a drowned miller knocks from beneath the wheel when debts go unpaid.",
            },
        ]
    }
    _seed_npc_profiles(
        simulation_state,
        {
            "npc:Elian": {
                "npc_id": "npc:Elian",
                "name": "Elian",
                "role": "Miller",
                "history": "Elian locked the mill after hearing knocking from inside.",
                "biography": "A proud worker shaken by fear and public blame.",
                "growth": "Begins ashamed and afraid; may regain courage if the truth is found.",
                "growth_stage": "frightened_miller",
            },
            "npc:Sister Vale": {
                "npc_id": "npc:SisterVale",
                "name": "Sister Vale",
                "role": "Village Priest",
                "history": "Sister Vale has been asked to bless the mill but doubts the simple ghost story.",
                "biography": "Calm, observant, and careful about superstition.",
                "growth": "Begins cautious; may support either spiritual or practical resolution.",
                "growth_stage": "careful_priest",
            },
        },
    )
    _seed_arc(
        simulation_state,
        arc_id="arc:haunted_mill",
        title="Haunted Mill",
        stage="locked_wheelhouse",
        pressure=50,
        milestones=[
            {
                "milestone_id": "milestone:enter_mill",
                "title": "Enter the mill",
                "objective_text": "Find a safe way into Graywater Mill.",
                "status": "active",
                "priority": 90,
            },
            {
                "milestone_id": "milestone:investigate_knocking",
                "title": "Investigate the knocking",
                "objective_text": "Determine what is making sounds inside the wheelhouse.",
                "status": "active",
                "priority": 80,
            },
            {
                "milestone_id": "milestone:restore_mill",
                "title": "Restore the mill",
                "objective_text": "Resolve the threat so the town's mill can work again.",
                "status": "active",
                "priority": 70,
            },
        ],
    )
    _seed_initial_journal(
        simulation_state,
        entry_id="journal:haunted_mill:start",
        title="The Silent Mill",
        text="Graywater Mill has stopped, and the town fears a haunting.",
    )
    _seed_event(
        simulation_state,
        event_id="event:haunted_mill:silent_wheel",
        title="Silent Wheel",
        summary="The town's mill has stopped after strange lights and knocking.",
        severity="medium",
    )
    return {"ok": True, "seed": "haunted_mill_seed", "hook_result": {"ok": True}}


def seed_noble_blackmail_campaign(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    _reset_seed_roots(simulation_state)
    _seed_common_player(simulation_state, gold=20, silver=4)
    simulation_state["campaign_director_state"] = {
        "campaign_title": "Letters Beneath the Seal",
        "premise": "A minor noble hires the player after blackmail letters threaten to expose a secret before the midsummer court.",
        "dramatic_question": "Can the player uncover the blackmailer without becoming a pawn in court politics?",
        "opening_tension": "Every suspect has something to gain, and every truth carries social cost.",
        "director_goals": [
            "Introduce intrigue instead of wilderness investigation.",
            "Create social choices with reputation consequences.",
            "Branch toward loyalty, exposure, or double-cross.",
        ],
        "stakes": [
            "A household may collapse.",
            "An innocent servant may be blamed.",
            "The player may gain or lose noble favor.",
        ],
    }
    simulation_state["lore_state"] = {
        "entries": [
            {
                "id": "lore:midsummer_court",
                "title": "Midsummer Court",
                "text": "A seasonal gathering where alliances, marriages, debts, scandals, and secrets become weapons.",
            },
            {
                "id": "lore:wax_seals",
                "title": "Wax Seals and Secret Letters",
                "text": "Among minor nobles, forged seals and intercepted letters can ruin families faster than swords.",
            },
        ]
    }
    _seed_npc_profiles(
        simulation_state,
        {
            "npc:LadyArven": {
                "npc_id": "npc:LadyArven",
                "name": "Lady Arven",
                "role": "Minor Noble",
                "history": "Lady Arven received blackmail letters before court.",
                "biography": "Composed in public but privately cornered.",
                "growth": "Begins controlling and guarded; may learn to trust or manipulate the player.",
                "growth_stage": "cornered_patron",
            },
            "npc:Perrin": {
                "npc_id": "npc:Perrin",
                "name": "Perrin",
                "role": "House Steward",
                "history": "Perrin manages household correspondence and knows who handles seals.",
                "biography": "Precise, loyal, and possibly too knowledgeable.",
                "growth": "Begins formal; may become ally, suspect, or scapegoat.",
                "growth_stage": "formal_steward",
            },
        },
    )
    _seed_arc(
        simulation_state,
        arc_id="arc:noble_blackmail",
        title="Noble Blackmail",
        stage="sealed_threat",
        pressure=60,
        milestones=[
            {
                "milestone_id": "milestone:inspect_letters",
                "title": "Inspect the letters",
                "objective_text": "Examine the blackmail letters, seals, handwriting, and delivery method.",
                "status": "active",
                "priority": 90,
            },
            {
                "milestone_id": "milestone:question_household",
                "title": "Question the household",
                "objective_text": "Interview servants, stewards, and visitors without causing scandal.",
                "status": "active",
                "priority": 80,
            },
            {
                "milestone_id": "milestone:identify_blackmailer",
                "title": "Identify the blackmailer",
                "objective_text": "Find who is using the secret and decide what to do with the truth.",
                "status": "active",
                "priority": 70,
            },
        ],
    )
    _seed_initial_journal(
        simulation_state,
        entry_id="journal:noble_blackmail:start",
        title="Letters Beneath the Seal",
        text="Lady Arven is being blackmailed before midsummer court.",
    )
    _seed_event(
        simulation_state,
        event_id="event:noble_blackmail:sealed_threat",
        title="Sealed Threat",
        summary="Blackmail letters threaten a noble household before court.",
        severity="high",
    )
    return {"ok": True, "seed": "noble_blackmail_seed", "hook_result": {"ok": True}}


def seed_campaign(simulation_state: Dict[str, Any], scenario_seed: str) -> Dict[str, Any]:
    if scenario_seed == "tavern_story_seed":
        return seed_tavern_story_campaign(simulation_state)
    if scenario_seed == "caravan_ambush_seed":
        return seed_caravan_ambush_campaign(simulation_state)
    if scenario_seed == "missing_apprentice_seed":
        return seed_missing_apprentice_campaign(simulation_state)
    if scenario_seed == "haunted_mill_seed":
        return seed_haunted_mill_campaign(simulation_state)
    if scenario_seed == "noble_blackmail_seed":
        return seed_noble_blackmail_campaign(simulation_state)
    raise ValueError(
        f"unknown_campaign_seed:{scenario_seed}; available={','.join(CAMPAIGN_SEED_NAMES)}"
    )