"""Rest (RQ-2.4; docs/rpg/design/items-and-rest.md): a night in a room paid for, a camp in the wild, or a while.

A pure rule: it reads where the hero stands, the rooms they have paid for and who rents rooms here, and says what
the rest does as changes. A full rest is the rest point a beaten hero wakes at, ends being battered and brings a
wound a night nearer healing (stakes.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    ConditionsChanged,
    HpChanged,
    NeedsChanged,
    ResourcesChanged,
    RestTaken,
    ServiceUsed,
    StateChange,
)
from app.apps.rpg.rules.combat.stakes import BATTERED, WOUND_RESTS, WOUNDED, conditions
from app.apps.rpg.foundation.state import access as _sections

_SLEEP = re.compile(r"\b(sleep|slumber|bed|night|room)\b")
_CAMP = re.compile(r"\b(camp|bedroll|tent)\b")
# kind: (minutes, fatigue, share of missing HP restored, a full rest)
RESTS = {"room": (480, -60, 0.5, True), "camp": (480, -40, 0.25, True), "while": (60, -15, 0.0, False)}


@dataclass(frozen=True)
class RestOutcome:
    changes: list[StateChange] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    refused: bool = False
    minutes: int = 0
    kind: str = ""


def _room(simulation: Mapping[str, Any], location: str) -> dict[str, Any]:
    """A room the hero paid for from someone who rents rooms here."""
    providers = _d(_d(_sections.world_model_of(simulation)).get("providers"))
    for service in reversed(_l(simulation.get("active_services"))):
        service = _d(service)
        provider = _d(providers.get(_s(service.get("provider_id"))))
        if (service.get("status") == "active" and service.get("service_kind") == "lodging"
                and (not provider or _s(provider.get("location_id")) == location)):
            return service
    return {}


def _rooms_for_rent(simulation: Mapping[str, Any], location: str) -> list[str]:
    world = _d(_sections.world_model_of(simulation))
    lines = []
    for provider_id, provider in _d(world.get("providers")).items():
        provider = _d(provider)
        if _s(provider.get("location_id")) != location or "lodging" not in _l(provider.get("service_kinds")):
            continue
        for offer in _l(_d(world.get("offers")).get(provider_id)):
            offer = _d(offer)
            if offer.get("service_kind") == "lodging":
                lines.append(f"{_s(provider.get('provider_name'))} offers {_s(offer.get('label'))}")
    return lines


def _full_rest(simulation: Mapping[str, Any]) -> list[StateChange]:
    """Each of the party: battered ends, and a wound is a night nearer healing."""
    player = _d(_sections.player_state_of(simulation))
    party = [("player", player), *((_s(_d(row).get("npc_id")), _d(row))
                                   for row in _l(_d(_sections.party_state_of(player)).get("companions")) if _d(row).get("npc_id"))]
    changes: list[StateChange] = []
    for actor_id, actor in party:
        held = conditions(actor)
        kept = []
        for condition in held:
            if condition.get("kind") == BATTERED:
                continue
            if condition.get("kind") == WOUNDED:
                left = int(condition.get("rests_left") or WOUND_RESTS) - 1
                if left <= 0:
                    continue
                condition = {**condition, "rests_left": left}
            kept.append(condition)
        if kept != held:
            changes.append(ConditionsChanged(actor_id=actor_id, conditions=tuple(kept)))
    return changes


def rest(simulation: Mapping[str, Any], text: str) -> RestOutcome:
    player = _d(_sections.player_state_of(simulation))
    location = _s(player.get("location_id"))
    lowered = text.casefold()
    room = _room(simulation, location)
    if _CAMP.search(lowered):
        kind = "camp"
    elif _SLEEP.search(lowered) or room:
        kind = "room" if room else "camp"
        if not room:
            for_rent = _rooms_for_rent(simulation, location)
            if for_rent:  # a bed here costs coin: no sleeping in the street
                return RestOutcome(lines=[f"You have no room here to sleep in. {'; '.join(for_rent)}."],
                                   refused=True)
    else:
        kind = "while"
    minutes, fatigue, share, full = RESTS[kind]
    hp = _d(_d(player.get("resources")).get("hp"))
    restored = int((int(hp.get("max") or 0) - int(hp.get("current") or 0)) * share)
    changes: list[StateChange] = [NeedsChanged(fatigue=fatigue)]
    if restored > 0:
        changes.append(HpChanged(delta=restored))
    # Stamina and mana (what the hero's abilities spend) come back in full with a night's rest, else by health's share.
    pools = {name: _d(_d(player.get("resources")).get(name)) for name in ("stamina", "mana")}
    back = {name: int((int(pool.get("max") or 0) - int(pool.get("current") or 0)) * (1 if full else share))
            for name, pool in pools.items()}
    if back["stamina"] > 0 or back["mana"] > 0:
        changes.append(ResourcesChanged(stamina=back["stamina"], mana=back["mana"], reason="rest"))
    if room:
        changes.append(ServiceUsed(offer_id=_s(room.get("offer_id"))))
    if full:
        changes.append(RestTaken(location_id=location))
        changes.extend(_full_rest(simulation))
    hours = minutes // 60
    duration = f"{hours} hour{'s' if hours != 1 else ''}"
    said = {
        "room": f"You rest through the night in the room you paid for ({_s(room.get('label')).casefold() or 'a room'}, "
                f"{duration}).",
        "camp": f"You make camp and rest through the night ({duration}).",
        "while": f"You rest a while ({duration}).",
    }[kind]
    lines = [said + (f" It restores {restored} health." if restored else "")]
    return RestOutcome(changes, lines, minutes=minutes, kind=kind)


__all__ = ["RESTS", "RestOutcome", "rest"]
