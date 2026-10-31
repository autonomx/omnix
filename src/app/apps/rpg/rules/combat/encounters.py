"""An encounter the game master sets (evolution roadmap EV-0): a creature of the bestiary, sized to the hero's level.
Pure.

The game master proposes; this rule decides. It folds the proposal in when the creature is the world's, its danger is
within the hero's level budget (``rules/budgets.py``), the hero stands where the world's creatures are met (somewhere
no one lives) and no fight is on, and the day's limit holds; then the creature bars the hero's way, as one met on a
dangerous road does (the fight rule's ``confront``).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.proposals import Folded, refused


def fold_encounter(document: Mapping[str, Any], payload: Mapping[str, Any]) -> Folded:
    from app.apps.rpg.rules import routines
    from app.apps.rpg.rules.budgets import encounter_fits
    from app.apps.rpg.rules.combat.campaign_mechanics import campaign_creature_definition
    from app.apps.rpg.rules.combat.fight import fight
    from app.apps.rpg.rules.direction import allows, counted

    simulation = _d(_sections.simulation_state_of(document))
    creature = campaign_creature_definition(simulation, _s(payload.get("creature_id")))
    if creature is None:
        return refused("no such creature in this world")
    if _d(_sections.combat_state_of(simulation)).get("active") is True:
        return refused("a fight is already on")
    if not routines.is_wild(simulation):
        return refused("the world's creatures are met where no one lives")
    level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
    if creature.get("boss") or not encounter_fits(simulation, [creature], level):
        return refused("it is beyond the hero's level's danger budget")
    limit = allows(simulation, "encounter")
    if limit:
        return refused(limit)
    turns = int(_d(document.get("state")).get("turn_count") or 0)
    met = fight(simulation, action="confront", target_ref=_s(creature.get("definition_id")), turn_key=f"gm:{turns}")
    if met is None or met.refused:
        return refused(" ".join(met.lines) if met else "it cannot be fought here")
    return Folded([*met.changes, counted(simulation, "encounter")])


__all__ = ["fold_encounter"]
