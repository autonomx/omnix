"""
System Trigger Engine — evaluates cross-system interactions for emergence.

Scans the current world state (economy, NPC emotions, resources, faction
relations) and generates ``PendingConsequence`` objects that represent
emergent events no-one explicitly scripted.  This creates a living world
where famine causes crime, anger escalates to conflict, and resource
scarcity drives NPC behaviour changes.
"""

from typing import Any, Dict, List

from app.rpg.models import GameSession, PendingConsequence


def evaluate_system_triggers(session: GameSession) -> List[PendingConsequence]:
    """
    Scan the session for cross-system trigger conditions and return new
    consequences that should be queued.

    Called once per turn, after the world tick and before the consequence
    engine fires.
    """
    new_events: List[PendingConsequence] = []

    # --- Economy → Crime (low market modifier means economic decline) ------
    for loc in session.world.locations:
        if loc.market_modifier < 0.7:
            new_events.append(PendingConsequence(
                trigger_turn=session.turn_count + 1,
                source_event="economic_decline",
                narrative=f"Crime rises in {loc.name} as the economy falters...",
                type="world",
                visibility="foreshadowed",
                effect_diff={
                    "npc_changes": {},  # no direct NPC diff — crime is a mood
                },
                importance=0.6,
            ))

    # --- NPC Emotion → Conflict (high anger triggers confrontation) --------
    for npc in session.npcs:
        anger = npc.emotional_state.get("anger", 0)
        if anger > 0.8:
            new_events.append(PendingConsequence(
                trigger_turn=session.turn_count + 1,
                source_event=f"{npc.name}_anger",
                narrative=f"{npc.name} is on the verge of violence...",
                type="npc",
                visibility="visible",
                effect_diff={
                    "npc_changes": {
                        npc.name: {"current_action": "confront"},
                    },
                },
                importance=0.7,
            ))

    # --- Resource scarcity → World events ----------------------------------
    resources = session.world.resources
    food = resources.get("food", 100)
    security = resources.get("security", 100)

    if food < 30:
        new_events.append(PendingConsequence(
            trigger_turn=session.turn_count + 2,
            source_event="famine",
            narrative="Famine spreads — people grow desperate...",
            type="world",
            visibility="visible",
            effect_diff={},
            importance=0.8,
        ))

    if security < 30:
        new_events.append(PendingConsequence(
            trigger_turn=session.turn_count + 1,
            source_event="bandit_rise",
            narrative="Bandits roam freely as security crumbles...",
            type="world",
            visibility="foreshadowed",
            effect_diff={},
            importance=0.7,
        ))

    # --- Faction tension → Conflict ----------------------------------------
    for faction in session.world.factions:
        for other_name, relation in faction.relations.items():
            if relation < -50:
                new_events.append(PendingConsequence(
                    trigger_turn=session.turn_count + 2,
                    source_event=f"faction_tension_{faction.name}_{other_name}",
                    narrative=f"Tensions between {faction.name} and {other_name} near breaking point...",
                    type="narrative",
                    visibility="foreshadowed",
                    effect_diff={},
                    importance=0.8,
                ))

    return new_events


def update_resources(session: GameSession) -> None:
    """
    Simulate resource changes based on world state.

    Called during the world tick to create slow resource drift that feeds
    into the system trigger evaluation.
    """
    resources = session.world.resources

    # Each location with a high market modifier generates gold
    for loc in session.world.locations:
        if loc.market_modifier > 1.2:
            resources["gold"] = min(200, resources.get("gold", 100) + 2)
        elif loc.market_modifier < 0.7:
            resources["gold"] = max(0, resources.get("gold", 100) - 2)

    # Active world events can drain resources
    for event in session.world.active_world_events:
        if event.type == "war":
            resources["security"] = max(0, resources.get("security", 100) - 5)
            resources["food"] = max(0, resources.get("food", 100) - 3)
        elif event.type == "plague":
            resources["food"] = max(0, resources.get("food", 100) - 5)
        elif event.type == "festival":
            resources["gold"] = max(0, resources.get("gold", 100) - 2)
            resources["food"] = max(0, resources.get("food", 100) - 1)

    # Natural regeneration
    resources["food"] = min(200, resources.get("food", 100) + 1)
    resources["security"] = min(200, resources.get("security", 100) + 1)
