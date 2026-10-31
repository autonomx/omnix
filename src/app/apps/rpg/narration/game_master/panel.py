"""Talking to the game master (evolution roadmap EV-0, part 1; owner decision, question 12).

The player asks the game master about the campaign, as at a table ("What is going on in Valecourt?", "What did I
promise Orik?"). One call answers, off the turn's path, from what the hero knows only (EV-1's record): the entries they
met, visited or heard of, the facts they learned, what people told them, their quests and party, where they stand,
and the reasons the game master gave for its own proposals once folded in, when what they name is known. No secret,
no unmet entry and no plan not yet played reaches the prompt.

Code checks every answer before it is shown: it names no secret (``names_a_secret``) and no entry of the world the
hero does not know; else it is withheld. A question is not a turn: it changes nothing. Asked to act, it declines. The
call may propose a wish for the story (a pace, danger, tone, or someone to follow), which the panel offers as a card
to confirm (``rules/direction.note_preference``). Questions count, with turns, against the hourly model budget.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.narration.world_data import RULE as WORLD_DATA_RULE, world_data
from app.prompts import prompt_template

logger = logging.getLogger(__name__)
PANEL_TIMEOUT_SECONDS = 30.0
WITHHELD = "That is not something I can tell you yet."
_PROMPT = prompt_template(
    "rpg.game_master.panel", "1",
    "You are the game master of this campaign, talking with the player at the table. Answer their question in two to "
    "four sentences, from KNOWN only: what has happened and why, the situation now, and options or hints as a game "
    "master would give them. Never tell a secret, anything the hero has not learned, or what you plan. You change "
    "nothing in the game: asked to act or to give something, decline. When the player says how they want the story to "
    "go, you may propose one wish from WISHES. Reply with JSON only: {{\"answer\": \"...\", \"wish\": null or "
    "{{\"kind\": \"...\", \"value\": \"...\"}}}}. " + WORLD_DATA_RULE + "\nPLAYER: {v0}\nCONTEXT: ",
)


def known_view(document: Mapping[str, Any]) -> dict[str, Any]:
    """What the hero knows, as the panel's prompt holds it: public text only, and only of entries they know."""
    from app.apps.rpg.rules.consequences import world_facts
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.direction import wishes
    from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries
    from app.apps.rpg.rules.routines import companions, hero_location, present_now
    from app.apps.rpg.rules.secrets import for_the_model

    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    secrets = list(secrets_held(world.get("npcs")))
    known = known_entries(simulation)
    entries = world_entries(simulation)
    view_of = {"person": ("name", "role", "description"), "place": ("name", "description", "region_name"),
               "group": ("name", "summary"), "quest": ("title", "objective"), "item": ("name", "type", "effect"),
               "creature": ("name", "threat")}
    met = {entry_id: {"how": how, **{key: entries[entry_id].get(key) for key in view_of[entries[entry_id]["family"]]
                                     if entries[entry_id].get(key)}}
           for entry_id, how in known.items() if entry_id in entries}
    told = [_s(_d(fact).get("text")) for row in _l(world.get("knowledge")) for fact in _l(_d(row).get("facts"))
            if _s(_d(fact).get("fact_id")) in {str(fact_id) for ids in _d(_d(simulation.get("dialogue")).get(
                "known_facts")).values() for fact_id in _l(ids)}]
    quests = [{"title": _d(row).get("title"), "status": _d(row).get("status"), "objective": _d(row).get("objective")}
              for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))
              if _s(_d(row).get("quest_id") or _d(row).get("id")) in known]
    view = {
        "known": met, "told": told, "quests": quests,
        "learned": [row.get("told") for row in world_facts(simulation).values()
                    if row.get("known") is True and row.get("told")],
        "at": hero_location(simulation), "present": [npc for npc in present_now(simulation)[1] if npc in known],
        "companions": companions(simulation), "wishes": wishes(simulation),
    }
    return for_the_model(view, secrets)


def _unknown_names(document: Mapping[str, Any]) -> list[str]:
    """The names of the world's entries the hero does not know (an answer naming one is withheld)."""
    from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries

    simulation = _d(_sections.simulation_state_of(document))
    known = known_entries(simulation)
    names = []
    for entry_id, row in world_entries(simulation).items():
        if entry_id in known:
            continue
        name = _s(row.get("name") or row.get("title"))
        if len(name) > 3:
            names.append(name)
    return names


def answer_is_safe(document: Mapping[str, Any], answer: str) -> bool:
    """Code's check of an answer before it is shown: no secret named, no entry the hero does not know named."""
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.secrets import names_a_secret

    world = _d(_sections.world_model_of(_d(_sections.simulation_state_of(document))))
    if names_a_secret(answer, list(secrets_held(world.get("npcs")))):
        return False
    lowered = answer.casefold()
    return not any(re.search(rf"(?<![\w']){re.escape(name.casefold())}(?![\w'])", lowered)
                   for name in _unknown_names(document))


def ask(document: Mapping[str, Any], question: str) -> dict[str, Any]:
    """The game master's answer to ``question`` (or that it was withheld), and the wish it proposes, checked."""
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway
    from app.apps.rpg.rules.direction import WISHES, note_preference

    gateway = build_app_llm_gateway()
    if gateway is None:
        return {"answer": "The game master is away: no model is set up.", "withheld": False, "wish": None}
    context = {"KNOWN": known_view(document), "WISHES": {kind: list(values) for kind, values in WISHES.items()}}
    prompt = _PROMPT.format(v0=question[:600]) + world_data(context)
    try:
        raw = _s(gateway.generate(prompt, timeout_s=PANEL_TIMEOUT_SECONDS,
                                  provider_options={"temperature": 0.4, "max_tokens": 300}))
    except Exception:
        logger.warning("rpg_game_master_panel_failed", exc_info=True)
        return {"answer": "The game master could not answer just now.", "withheld": False, "wish": None}
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    try:
        payload = _d(json.loads(match.group(0))) if match else {"answer": raw}
    except json.JSONDecodeError:
        payload = {"answer": raw}
    answer = _s(payload.get("answer")).strip()[:1500]
    safe = bool(answer) and answer_is_safe(document, answer)
    wish = _d(payload.get("wish"))
    simulation = _d(_sections.simulation_state_of(document))
    offered = None
    if wish and not note_preference(simulation, _s(wish.get("kind")), _s(wish.get("value"))).refused:
        offered = {"kind": _s(wish.get("kind")), "value": _s(wish.get("value"))}
    return {"answer": answer if safe else WITHHELD, "withheld": not safe, "wish": offered}


__all__ = ["WITHHELD", "answer_is_safe", "ask", "known_view"]
