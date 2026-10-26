"""Where a campaign document keeps its sections, named once (AL020).

Each accessor returns what its holder keeps under the section's key, as the holder keeps it (the same object, or
``None`` when it keeps none): a caller that read ``holder.get("player_state")`` reads ``player_state_of(holder)``
and nothing else changes. The holders are the document (its simulation and runtime state), the simulation (the
hero, the world model, the people, quests, fights) and the hero (their pack and party). The typed models of the
sections are ``sections.py``'s; this is where their keys live.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _kept(holder: Any, key: str) -> Any:
    return holder.get(key) if isinstance(holder, Mapping) else None


def simulation_state_of(document: Any) -> Any:
    return _kept(document, "simulation_state")


def runtime_state_of(document: Any) -> Any:
    return _kept(document, "runtime_state")


def player_state_of(simulation: Any) -> Any:
    return _kept(simulation, "player_state")


def world_model_of(simulation: Any) -> Any:
    return _kept(simulation, "world_model")


def npc_index_of(holder: Any) -> Any:
    """The people's index: the simulation's, or the runtime's copy of it."""
    return _kept(holder, "npc_index")


def present_npc_state_of(simulation: Any) -> Any:
    return _kept(simulation, "present_npc_state")


def quest_state_of(simulation: Any) -> Any:
    return _kept(simulation, "quest_state")


def combat_state_of(simulation: Any) -> Any:
    return _kept(simulation, "combat_state")


def survival_of(simulation: Any) -> Any:
    return _kept(simulation, "survival")


def economy_state_of(simulation: Any) -> Any:
    return _kept(simulation, "economy_state")


def travel_state_of(simulation: Any) -> Any:
    return _kept(simulation, "travel_state")


def inventory_state_of(player: Any) -> Any:
    """The hero's pack: the store the reducer keeps (``player_state.inventory_state``)."""
    return _kept(player, "inventory_state")


def party_state_of(player: Any) -> Any:
    return _kept(player, "party_state")


ACCESSORS = {
    "simulation_state": simulation_state_of, "runtime_state": runtime_state_of, "player_state": player_state_of,
    "world_model": world_model_of, "npc_index": npc_index_of, "present_npc_state": present_npc_state_of,
    "quest_state": quest_state_of, "combat_state": combat_state_of, "survival": survival_of,
    "economy_state": economy_state_of, "travel_state": travel_state_of, "inventory_state": inventory_state_of,
    "party_state": party_state_of,
}


# The fields the turn path reads straight off the simulation and the runtime state, named here once as well.

def rng_seed_of(simulation: Any) -> Any:
    return _kept(simulation, "rng_seed")


def campaign_rules_of(simulation: Any) -> Any:
    return _kept(simulation, "campaign_rules")


def campaign_mechanics_of(simulation: Any) -> Any:
    return _kept(simulation, "campaign_mechanics")


def campaign_end_of(simulation: Any) -> Any:
    return _kept(simulation, "campaign_end")


def presentation_state_of(simulation: Any) -> Any:
    return _kept(simulation, "presentation_state")


def memory_state_of(simulation: Any) -> Any:
    return _kept(simulation, "memory_state")


def climate_survival_of(simulation: Any) -> Any:
    return _kept(simulation, "climate_survival")


def needs_of(simulation: Any) -> Any:
    return _kept(simulation, "needs")


def interaction_seq_of(runtime: Any) -> Any:
    return _kept(runtime, "interaction_seq")


def state_revision_of(runtime: Any) -> Any:
    return _kept(runtime, "state_revision")


def campaign_calendar_of(runtime: Any) -> Any:
    return _kept(runtime, "campaign_calendar")


def player_journal_of(runtime: Any) -> Any:
    return _kept(runtime, "player_journal")


def causal_applied_turn_keys_of(runtime: Any) -> Any:
    return _kept(runtime, "causal_applied_turn_keys")


def performance_of(runtime: Any) -> Any:
    return _kept(runtime, "performance")


FIELD_ACCESSORS = {
    "rng_seed": rng_seed_of, "campaign_rules": campaign_rules_of, "campaign_mechanics": campaign_mechanics_of,
    "campaign_end": campaign_end_of, "presentation_state": presentation_state_of, "memory_state": memory_state_of,
    "climate_survival": climate_survival_of, "needs": needs_of, "interaction_seq": interaction_seq_of,
    "state_revision": state_revision_of, "campaign_calendar": campaign_calendar_of,
    "player_journal": player_journal_of, "causal_applied_turn_keys": causal_applied_turn_keys_of,
    "performance": performance_of,
}

__all__ = [*sorted(accessor.__name__ for table in (ACCESSORS, FIELD_ACCESSORS) for accessor in table.values()),
           "ACCESSORS", "FIELD_ACCESSORS"]
