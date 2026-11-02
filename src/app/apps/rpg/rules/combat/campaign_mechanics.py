"""Consume campaign-local compiled mechanics in deterministic combat."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from app.apps.rpg.foundation.state import access as _sections


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def campaign_mechanics_catalog(simulation_state: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(_sections.campaign_mechanics_of(simulation_state))


def campaign_creature_definition(
    simulation_state: Mapping[str, Any],
    creature_ref: str,
) -> dict[str, Any] | None:
    creatures = _mapping(
        campaign_mechanics_catalog(simulation_state).get("creatures")
    )
    wanted = _text(creature_ref)
    wanted_slug = _slug(wanted.removeprefix("creature:"))
    for definition_id, raw in creatures.items():
        definition = _mapping(raw)
        names = {
            _text(definition_id).casefold(),
            _text(definition.get("definition_id")).casefold(),
            _text(definition.get("name")).casefold(),
            _slug(_text(definition.get("name"))),
        }
        if wanted.casefold() in names or wanted_slug in names:
            return definition
    # "the echo wolf with my dagger": the creature the words name (the longest name, as whole words).
    words = f" {' '.join(re.findall(r'[a-z0-9]+', wanted.casefold()))} "
    named = [
        _mapping(raw)
        for raw in creatures.values()
        if _slug(_text(_mapping(raw).get("name"))) and f" {_slug(_text(_mapping(raw).get('name'))).replace('-', ' ')} " in words
    ]
    return max(named, key=lambda row: len(_text(row.get("name")))) if named else None


def instantiate_campaign_creature(
    simulation_state: Mapping[str, Any],
    creature_ref: str,
    *,
    instance_index: int = 1,
) -> dict[str, Any] | None:
    definition = campaign_creature_definition(simulation_state, creature_ref)
    if definition is None:
        return None
    definition_id = _text(definition.get("definition_id"))
    actor_id = f"enemy:{_slug(definition_id)}:{max(1, int(instance_index))}"
    hp = max(1, int(definition.get("hp") or 1))
    return {
        "actor_id": actor_id,
        "enemy_id": actor_id,
        "definition_id": definition_id,
        "definition_revision": int(definition.get("definition_revision") or 1),
        "name": _text(definition.get("name")) or definition_id,
        "side": "enemy",
        "level": int(definition.get("level") or 1),
        "hp": hp,
        "max_hp": hp,
        "defense": int(definition.get("defense") or 10),
        "armor": int(definition.get("armor") or 0),
        "damage_min": int(definition.get("damage_min") or 1),
        "damage_max": int(definition.get("damage_max") or 3),
        "accuracy_bonus": int(definition.get("accuracy_bonus") or 0),
        "initiative_bonus": int(definition.get("initiative_bonus") or 0),
        "morale_threshold": int(definition.get("morale_threshold") or 35),
        "tags": list(definition.get("tags") or ()),
        "loot_table_id": _text(definition.get("loot_table_id")),
        "xp_value": int(definition.get("xp_value") or 0),
        "budget_cost": int(definition.get("budget_cost") or 1),
        "condition_immunities": list(
            definition.get("condition_immunities") or ()
        ),
        "vulnerabilities": deepcopy(list(definition.get("vulnerabilities") or ())),
        # EV-2: copied into the fight when the creature joins it, as its behaviour is.
        "resists": [_text(tag).casefold() for tag in definition.get("resists") or () if _text(tag)],
        "phases": deepcopy(list(definition.get("phases") or ())),
        "no_escape": definition.get("no_escape") is True,
        "recovers": float(raw_recovers if (raw_recovers := definition.get("recovers")) is not None else 1.0),
        "behaviour": _text(definition.get("behaviour")) or "fights",
        "speaks": definition.get("speaks") is True,
        "status": "active",
        "status_effects": [],
        "mechanics_source": "campaign_mechanics_catalog",
    }
