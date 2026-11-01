"""The game master's direction call (evolution roadmap EV-0, part 1): after a turn commits, off its path.

When the turn ends a scene (the hero arrived somewhere), comes back after time away, or play has stalled
(``rules/direction.STALL_TURNS`` turns with nothing meaningful), a job asks the reference model what should happen
next, and why. Its prompt holds the public canon only (``rules/secrets.for_the_model``: no secret field, no sentence
telling one), the campaign's state as it stands, the facts, the open threads, the player's wishes and the world's
palette (its creatures sized to the hero, its quests, its people and places). It answers with proposals from a closed
set. Code checks each mechanically before it is stored: its kind is one the record folds in, every id it names exists,
its text names no secret, a person it moves is not protected; then the proposals go to the proposal record (EV-11),
and the next turn folds them in through their owning rules, which check them again. Nothing here writes the campaign.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.proposals import Proposal
from app.apps.rpg.narration.world_data import RULE as WORLD_DATA_RULE, world_data
from app.prompts import prompt_template

logger = logging.getLogger(__name__)
DIRECTION_TIMEOUT_SECONDS = 60.0
MAX_PROPOSALS = 3
KINDS = ("gm_fact", "gm_complication", "gm_quest_offer", "gm_move_person", "gm_encounter", "gm_beat", "gm_rumour",
         "gm_invent")
_PROMPT = prompt_template(
    "rpg.game_master.direction", "3",
    "You are the game master of a role-playing campaign. Decide what should happen next in the world, and why: pace "
    "a stalled story with a complication or an opportunity, bring a past choice back, move a person toward their "
    "goals (bring the next beat of a goal forward), send word about, set an encounter, or offer a quest. Propose at "
    "most three things, each one of KINDS, naming only ids in WORLD. Never write the hero's actions or their outcome; never set a reward. Reply with JSON only: "
    "{{\"proposals\": [{{\"kind\": \"...\", \"payload\": {{}}, \"reason\": \"...\"}}]}}. Payloads: gm_fact "
    "{{\"fact\", \"value\", \"told\"}}; gm_complication {{\"told\"}}; gm_quest_offer {{\"quest_id\"}}; gm_move_person "
    "{{\"npc_id\", \"location_id\", \"activity\"}}; gm_encounter {{\"creature_id\"}}; gm_beat {{\"npc_id\", "
    "\"goal_id\"}}; gm_rumour {{\"location_id\", \"told\"}}; gm_invent, only when the story needs someone or "
    "something WORLD lacks, {{\"family\": person|place|item|creature|quest, \"name\", \"description\", \"play\"}} "
    "with play as BUDGETS bounds it: a person {{\"location_id\", \"role\", \"schedule\", \"knowledge\"}}, a place "
    "{{\"roads\": [{{\"to\", \"travel_time\"}}]}}, an item {{\"type\", \"equipment\", \"location_id\" or "
    "\"seller_id\" and \"price_copper\"}}, a creature {{\"level\", \"hp\", \"damage_max\", \"defense\", "
    "\"weakness\"}}, a quest {{\"giver_id\", \"objective\", \"steps\", \"reward\"}}. Propose nothing when nothing "
    "should happen. " + WORLD_DATA_RULE + "\nWHY_NOW: {v0}\nCONTEXT: ",
)


def trigger(result: Mapping[str, Any], document: Mapping[str, Any]) -> str:
    """Why the game master is asked after this turn ("" when it is not): a scene ended (the hero arrived somewhere),
    a return after time away, or a stall."""
    from app.apps.rpg.rules.direction import STALL_TURNS, stall

    pipeline = _d(result.get("turn_pipeline"))
    changes = [_s(_d(row).get("type")) for row in _l(pipeline.get("changes"))]
    if pipeline.get("kind") == "world_tick":
        return "the hero came back after time away"
    if "location_changed" in changes:
        return "the hero arrived somewhere: a scene ended"
    simulation = _d(_sections.simulation_state_of(document))
    turns = int(_d(document.get("state")).get("turn_count") or 0)
    stalled = stall(simulation, turns)
    if stalled >= STALL_TURNS and stalled % STALL_TURNS == 0:  # once each stretch of stalled turns, not every turn
        return f"nothing meaningful has happened for {stalled} turns"
    return ""


def _palette(simulation: Mapping[str, Any]) -> dict[str, Any]:
    """The world as the game master may use it: public canon only, its creatures sized to the hero."""
    from app.apps.rpg.rules.budgets import encounter_fits
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.secrets import for_the_model

    world = _d(_sections.world_model_of(simulation))
    secrets = list(secrets_held(world.get("npcs")))
    level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
    creatures = _d(_d(_sections.campaign_mechanics_of(simulation)).get("creatures"))
    from app.apps.rpg.rules.routines import goals, next_beat

    view = {
        "people": {npc_id: {key: _d(row).get(key) for key in ("name", "role", "location_id", "goals")}
                   for npc_id, row in _d(world.get("npcs")).items()},
        "beats": [{"npc_id": npc_id, "goal_id": _s(goal.get("goal_id")), "goal": _s(goal.get("summary")),
                   "next": _s(next_beat(simulation, npc_id, goal).get("id"))}
                  for npc_id, goal in goals(simulation) if next_beat(simulation, npc_id, goal)],
        "places": {place_id: {key: _d(row).get(key) for key in ("name", "description", "region_name")}
                   for place_id, row in _d(world.get("locations")).items()},
        "quests": {quest_id: {key: _d(row).get(key) for key in ("title", "objective", "giver_id")}
                   for quest_id, row in _d(world.get("quests")).items()},
        "creatures": {creature_id: {"name": _s(_d(row).get("name")), "level": _d(row).get("level")}
                      for creature_id, row in creatures.items()
                      if not _d(row).get("boss") and encounter_fits(simulation, [_d(row)], level)},
    }
    return for_the_model(view, secrets)


def _state(document: Mapping[str, Any]) -> dict[str, Any]:
    from app.apps.rpg.rules.consequences import world_facts
    from app.apps.rpg.rules.direction import protected, stall, wishes
    from app.apps.rpg.rules.routines import companions, hero_location, present_now

    simulation = _d(_sections.simulation_state_of(document))
    turns = int(_d(document.get("state")).get("turn_count") or 0)
    quests = [_d(row) for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))]
    return {
        "hero": {"level": _d(_sections.player_state_of(simulation)).get("level"), "at": hero_location(simulation),
                 "companions": companions(simulation)},
        "present": present_now(simulation)[1],
        "quests": [{"id": _s(row.get("quest_id") or row.get("id")), "title": row.get("title"), "status": row.get("status"),
                    "objective": row.get("objective")} for row in quests],
        "facts": {fact: row.get("value") for fact, row in world_facts(simulation).items()
                  if not fact.startswith("waived:")},
        "turns_without_event": stall(simulation, turns),
        "wishes": wishes(simulation),
        "protected": sorted(protected(simulation)),
    }


def _guide(simulation: Mapping[str, Any]) -> dict[str, Any]:
    """The author's notes for the game master, as a model may read them: an author's notes may hold secrets."""
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.secrets import for_the_model

    world = _d(_sections.world_model_of(simulation))
    return _d(for_the_model(_d(world.get("gm_guide")), list(secrets_held(world.get("npcs")))))


def _parse(raw: str) -> list[dict[str, Any]]:
    match = re.search(r"\{.*\}", _s(raw), flags=re.DOTALL)
    try:
        payload = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return []
    return [_d(row) for row in _l(_d(payload).get("proposals"))][:MAX_PROPOSALS]


def checked(document: Mapping[str, Any], rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """The proposals that pass code's checks before they are stored, and why the others did not: a kind the record
    folds in, ids that exist, no secret named in any of its text, no protected person moved."""
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.direction import protected
    from app.apps.rpg.rules.secrets import names_a_secret

    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    secrets = list(secrets_held(world.get("npcs")))
    creatures = _d(_d(_sections.campaign_mechanics_of(simulation)).get("creatures"))
    ids = {"npc_id": set(_d(world.get("npcs"))), "location_id": set(_d(world.get("locations"))),
           "quest_id": set(_d(world.get("quests"))), "creature_id": set(creatures)}
    kept, dropped = [], []
    for row in rows:
        kind, payload, reason = _s(row.get("kind")), _d(row.get("payload")), _s(row.get("reason"))[:500]
        missing = [key for key, known in ids.items() if key in payload and _s(payload[key]) not in known]
        texts = [reason, *(str(value) for value in payload.values() if isinstance(value, str))]
        why = ("no kind the record folds in" if kind not in KINDS else
               f"no such {missing[0].removesuffix('_id')}" if missing else
               "it names a secret" if any(text and names_a_secret(text, secrets) for text in texts) else
               "a protected person moves only with the hero"
               if kind == "gm_move_person" and _s(payload.get("npc_id")) in protected(simulation) else "")
        if why:
            dropped.append(f"{kind}: {why}")
            continue
        kept.append({"kind": kind, "payload": payload, "reason": reason})
    return kept, dropped


def direct(session_id: str, document: Mapping[str, Any], why: str, *, revision: int) -> dict[str, Any]:
    """Ask the game master, check what it proposes, and store what passes as proposals for the next turn."""
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway
    from app.apps.rpg.foundation.persistence.rpg_proposal_repository import record_proposals

    gateway = build_app_llm_gateway()
    if gateway is None:
        return {"proposed": 0, "dropped": [], "reason": "no model"}
    simulation = _d(_sections.simulation_state_of(document))
    from app.apps.rpg.rules.budgets import budget

    level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
    context = {"KINDS": list(KINDS), "WORLD": _palette(simulation), "STATE": _state(document),
               "BUDGETS": budget(simulation, level).model_dump(mode="json"),
               "GUIDE": _guide(simulation)}
    prompt = _PROMPT.format(v0=why[:200]) + world_data(context)
    try:
        raw = gateway.generate(prompt, timeout_s=DIRECTION_TIMEOUT_SECONDS,
                               provider_options={"temperature": 0.7, "max_tokens": 600})
    except Exception:
        logger.warning("rpg_game_master_direction_failed session=%s", session_id, exc_info=True)
        return {"proposed": 0, "dropped": [], "reason": "the model failed"}
    kept, dropped = checked(document, _parse(_s(raw)))
    proposals = [Proposal(proposal_id=f"gm:{session_id}:{revision}:{index}", kind=row["kind"], source="game_master",
                          after_revision=revision, reason=row["reason"], payload=row["payload"])
                 for index, row in enumerate(kept)]
    stored = record_proposals(session_id, proposals) if proposals else 0
    if dropped:
        logger.info("rpg_game_master_dropped session=%s dropped=%s", session_id, dropped)
    return {"proposed": stored, "dropped": dropped, "reason": why}


__all__ = ["KINDS", "checked", "direct", "trigger"]
