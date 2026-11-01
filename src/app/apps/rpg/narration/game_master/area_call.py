"""Areas filled in as the hero approaches (evolution roadmap EV-10): the game master's area call, off the turn.

When the hero arrives somewhere, the larger areas next to them (their own region and those its roads reach) that are
still open are filled in, one job an area, once a campaign. The game master writes what the area's lore calls for,
up to what its budget leaves missing (``rules/budgets.area_budget``: authored detail counts toward it): places and
sites (a site's rooms are laid out by code, ``rules/exploration.build_site``), people, creatures, things, quests,
rumours and lore. Each entry is checked here (its kind still wanted, its name new, no secret named) and stored as a
proposal (``gm_area``, EV-11); the turns after fold the entries in, a capped share a turn, places first, through
``rules/inventions.fold_area_entry``, which checks each as any invention. Nothing is written to the campaign here.
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
AREA_TIMEOUT_SECONDS = 90.0
MAX_ENTRIES = 24
_PROMPT = prompt_template(
    "rpg.game_master.area", "1",
    "You are the game master of a role-playing campaign, filling in an area of its world before the hero reaches it. "
    "From the AREA's lore and the world's PALETTE, write what the area holds, at most WANTED of each kind: places "
    "(a building, a district, a landmark), sites (a cave, a ruin, a dungeon, usually hidden, with rooms named and "
    "described), people (who live and work there), creatures, things, quests, rumours and lore (its history, "
    "customs, dangers). Keep every number inside BUDGETS. Name only ids in WORLD. Never tell a secret. Reply with "
    "JSON only: {{\"entries\": [{{\"kind\": \"place\"|\"site\"|\"person\"|\"creature\"|\"item\"|\"quest\"|\"rumour\""
    "|\"lore\", \"name\", \"description\", \"play\": {{}}, \"told\", \"hidden\", \"difficulty\", \"site\": "
    "{{\"theme\", \"rooms\": [{{\"name\", \"description\"}}], \"boss_id\"}}}}]}}. play is as an invention's: a place or "
    "site {{\"roads\": [{{\"to\", \"travel_time\"}}]}}; a person {{\"location_id\", \"role\", \"schedule\", "
    "\"knowledge\"}}; a creature {{\"level\", \"hp\", \"damage_max\", \"defense\", \"weakness\"}}; an item "
    "{{\"type\", \"equipment\", \"location_id\" or \"seller_id\" and \"price_copper\"}}; a quest {{\"giver_id\", "
    "\"objective\", \"steps\", \"reward\"}}. A rumour or lore is its line, told. " + WORLD_DATA_RULE
    + "\nAREA: {v0}\nCONTEXT: ",
)


def _region(simulation: Mapping[str, Any], place_id: str) -> str:
    return _s(_d(_d(_d(_sections.world_model_of(simulation)).get("locations")).get(place_id)).get("region_id"))


def open_areas(document: Mapping[str, Any]) -> list[str]:
    """The larger areas next to the hero that are still open: their own region, then those a road from any of its
    places reaches (the lead time is the hero's whole stay in the area, not their last step before leaving it)."""
    from app.apps.rpg.rules.routines import hero_location

    simulation = _d(_sections.simulation_state_of(document))
    here = hero_location(simulation)
    world = _d(_sections.world_model_of(simulation))
    area = _region(simulation, here)
    places = {here} | ({place for place in _d(world.get("locations")) if _region(simulation, place) == area}
                       if area else set())
    near = [here]
    for route in _l(world.get("routes")):
        start, end = _s(_d(route).get("from")), _s(_d(route).get("to"))
        near += [end] if start in places else [start] if end in places else []
    filled = _d(_sections.area_detail_of(simulation))
    areas = [_region(simulation, place) for place in near]
    return [area for area in dict.fromkeys(areas) if area and not _l(_d(filled.get(area)).get("entries"))]


def _wanted(simulation: Mapping[str, Any], area_id: str) -> dict[str, int]:
    from app.apps.rpg.rules.budgets import area_budget
    from app.apps.rpg.rules.inventions import _held

    return {kind: count - _held(simulation, area_id, kind) for kind, count in area_budget(simulation, area_id).items()
            if kind != "service" and count - _held(simulation, area_id, kind) > 0}


def checked(document: Mapping[str, Any], area_id: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """The entries that pass code's checks before they are stored, and why the others did not."""
    from app.apps.rpg.rules.consequences import names_a_secret_here
    from app.apps.rpg.rules.inventions import _known_names

    simulation = _d(_sections.simulation_state_of(document))
    wanted = _wanted(simulation, area_id)
    names = _known_names(simulation)
    kept, dropped = [], []
    for row in rows[:MAX_ENTRIES]:
        kind, name = _s(row.get("kind")), _s(row.get("name")).strip()
        texts = [name, _s(row.get("description")), _s(row.get("told"))]
        why = ("no kind the area still wants" if wanted.get(kind, 0) <= 0 else
               "no name" if kind not in {"rumour", "lore"} and not name else
               "its name clashes with the world's" if name and name.casefold() in names else
               "it names a secret" if any(text and names_a_secret_here(simulation, text) for text in texts) else "")
        if why:
            dropped.append(f"{kind or '?'}: {why}")
            continue
        wanted[kind] -= 1
        names.add(name.casefold())
        kept.append(row)
    return kept, dropped


def _parse(raw: str) -> list[dict[str, Any]]:
    match = re.search(r"\{.*\}", _s(raw), flags=re.DOTALL)
    try:
        payload = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return []
    return [_d(row) for row in _l(_d(payload).get("entries"))]


def fill_area(session_id: str, document: Mapping[str, Any], area_id: str, *, revision: int) -> dict[str, Any]:
    """Ask the game master to fill in ``area_id``, check what it writes, and store what passes as proposals."""
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway
    from app.apps.rpg.narration.game_master.direction_call import _palette
    from app.apps.rpg.rules.budgets import budget
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.secrets import for_the_model
    from app.apps.rpg.session.turn.proposals import record_proposals

    gateway = build_app_llm_gateway()
    if gateway is None:
        return {"proposed": 0, "dropped": [], "reason": "no model"}
    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    wanted = _wanted(simulation, area_id)
    if not wanted:
        return {"proposed": 0, "dropped": [], "reason": "the area holds all its budget"}
    level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
    secrets = list(secrets_held(world.get("npcs")))
    places = {place_id: {key: _d(row).get(key) for key in ("name", "description")}
              for place_id, row in _d(world.get("locations")).items() if _s(_d(row).get("region_id")) == area_id}
    context = {"WANTED": wanted, "BUDGETS": budget(simulation, level).model_dump(mode="json"),
               "WORLD": _palette(simulation), "AREA": for_the_model({"id": area_id, "places": places}, secrets),
               "PALETTE": for_the_model(_d(_d(_d(world.get("gm_guide")).get("areas")).get(area_id)), secrets)}
    prompt = _PROMPT.format(v0=area_id) + world_data(context)
    try:
        raw = gateway.generate(prompt, timeout_s=AREA_TIMEOUT_SECONDS,
                               provider_options={"temperature": 0.7, "max_tokens": 3000})
    except Exception:
        logger.warning("rpg_game_master_area_failed session=%s area=%s", session_id, area_id, exc_info=True)
        return {"proposed": 0, "dropped": [], "reason": "the model failed"}
    kept, dropped = checked(document, area_id, _parse(_s(raw)))
    proposals = [Proposal(proposal_id=f"area:{session_id}:{area_id}:{index}", kind="gm_area", source="area",
                          after_revision=revision, reason=f"filling in {area_id}",
                          payload={"area_id": area_id, "entry": row})
                 for index, row in enumerate(kept)]
    stored = record_proposals(session_id, proposals) if proposals else 0
    return {"proposed": stored, "dropped": dropped, "reason": f"fill:{area_id}"}


__all__ = ["checked", "fill_area", "open_areas"]
