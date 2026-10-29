"""Step 4: each mechanic's resolver says what happens, as changes; it reads the campaign and writes nothing.

Alongside the changes it states the facts the narrator is told (``outcome_lines``): the runtime decides, the
narrator tells.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state.changes import LocationChanged, StateChange, TimeAdvanced, TurnCounted
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.location_registry import current_location_id
from app.apps.rpg.rules.contracts import A_WHILE, said, sayable
from app.apps.rpg.session.turn.planning import PlannedAction
from app.apps.rpg.session.turn.world_tick import clock_minute
from app.apps.rpg.foundation.state import access as _sections

MINUTES_PER_TICK = 10  # docs/rpg/design/time.md


def resolve(planned: PlannedAction, document: Mapping[str, Any]) -> list[StateChange]:
    """The changes the action makes: the turn is counted and the time it took passes."""
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    count = int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1
    changes: list[StateChange] = [TurnCounted(turn_count=count)]
    simulation = _d(_sections.simulation_state_of(document))
    if not _s(_d(_sections.player_state_of(simulation)).get("location_id")):
        # A campaign created without placing the hero (the starter town until RQ-2.8) stands them where its
        # world begins, as the older turn path did on its first turn.
        changes.append(LocationChanged(location_id=current_location_id(dict(simulation))))
    if planned.ticks:
        changes.append(TimeAdvanced(ticks=planned.ticks, minutes=planned.ticks * MINUTES_PER_TICK))
    return changes


def outcome_lines(planned: PlannedAction, document: Mapping[str, Any]) -> list[str]:
    """What the hero perceives, as plain facts for the narration."""
    if planned.mechanic == "clarify":
        return [planned.question]
    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    location_id = _s(_d(_sections.player_state_of(simulation)).get("location_id") or simulation.get("location_id"))
    location = _d(_d(world.get("locations")).get(location_id))
    name = _s(location.get("name")) or _s(_d(document.get("state")).get("current_location_name")) or "this place"
    present = routines.described(simulation, routines.present_now(simulation)[1], clock_minute(document))
    if planned.mechanic == "wait":
        waited = planned.ticks * MINUTES_PER_TICK
        how_long = "a while" if waited == A_WHILE else said(waited)
        return [f"You wait {how_long} in {name}; time passes.", *([f"Around you: {', '.join(present)}."] if present else [])]
    if planned.target_id:  # a close look at one thing: what the world says of it
        looked = _looked_at(simulation, world, planned.target_id)
        if looked:
            return [looked]
    lines = [f"You look around {name}."]
    if present:
        lines.append(f"Here: {', '.join(present)}.")
    places = _d(world.get("locations"))
    exits = [_s(_d(places.get(_s(place_id))).get("name")) for place_id in _d(location.get("exits")).values()]
    exits = [place for place in dict.fromkeys(exits) if place]
    if exits:
        lines.append(f"Paths lead to {', '.join(exits)}.")
    return lines


def _looked_at(simulation: Mapping[str, Any], world: Mapping[str, Any], target_id: str) -> str:
    """A close look at one thing: a person, a place, a creature, an offer or something carried, by what the world says
    of it; "" for something it does not know."""
    from app.apps.rpg.foundation.safe_values import safe_list as _l

    person = _d(_d(world.get("npcs")).get(target_id))
    if person:
        secrets = tuple(_s(secret) for secret in _l(person.get("secrets")))
        role, about = _s(person.get("role")), sayable(_s(person.get("description")), secrets).rstrip(".")
        return (f"You look closely at {_s(person.get('name')) or target_id}" + (f", the {role}" if role else "")
                + (f": {about}." if about else "."))
    place = _d(_d(world.get("locations")).get(target_id))
    if place:
        return f"You look toward {_s(place.get('name')) or target_id}" + (
            f": {_s(place.get('description'))}" if _s(place.get("description")) else ".")
    creature = _d(_d(_d(simulation.get("campaign_mechanics")).get("creatures")).get(target_id))
    if creature:
        return f"You study the {_s(creature.get('name')) or target_id}."
    carried = _sections.inventory_state_of(_d(_sections.player_state_of(simulation)))
    for item in _l(_d(carried).get("items")):
        item = _d(item)
        if target_id in {_s(item.get("item_id")), _s(item.get("id"))}:
            about = _s(item.get("description")) or _s(_d(item.get("fields")).get("description"))
            return f"You look over your {_s(item.get('name')) or target_id}" + (f": {about}" if about else ".")
    for offers in _d(world.get("offers")).values():
        for offer in _l(offers):
            offer = _d(offer)
            if _s(offer.get("offer_id")) == target_id:
                return f"You look over {_s(offer.get('label')) or target_id}, which is for sale here."
    return ""


__all__ = ["outcome_lines", "resolve"]
