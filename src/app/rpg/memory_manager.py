"""
Memory Manager for the AI Role-Playing System.

Implements a 3-layer memory system for context optimization:
- Short-term: Last N turns (full detail)
- Mid-term: Summarized events
- Long-term: Full structured database (queried selectively)
"""

import logging
from typing import Any, Dict, List, Optional

from app.rpg.models import GameSession, HistoryEvent

logger = logging.getLogger(__name__)

SHORT_TERM_SIZE = 10


def get_short_term_events(session: GameSession) -> List[HistoryEvent]:
    """Get the last N events (short-term memory)."""
    return session.history[-SHORT_TERM_SIZE:]


def get_mid_term_summary(session: GameSession) -> str:
    """Get the mid-term summary of game events."""
    return session.mid_term_summary or ""


def build_context(session: GameSession) -> str:
    """
    Build the context string for LLM calls.

    Assembles relevant information from all memory layers:
    - World rules and current state
    - Current location details
    - Relevant NPCs (at current location)
    - Active quests
    - Mid-term summary
    - Recent events (short-term)
    """
    parts = []

    # World info
    world = session.world
    parts.append(f"World: {world.name} ({world.genre})")
    parts.append(f"Time: Day {world.day_count}, {world.time_of_day}")
    parts.append(f"Technology: {world.rules.technology_level}")
    parts.append(f"Magic: {world.rules.magic_system}")
    if world.rules.forbidden_items:
        parts.append(f"Forbidden items: {', '.join(world.rules.forbidden_items)}")
    if world.rules.custom_rules:
        parts.append(f"Special rules: {'; '.join(world.rules.custom_rules)}")

    # Player info
    player = session.player
    parts.append(f"\nPlayer: {player.name}")
    parts.append(f"Location: {player.location}")
    stats = player.stats
    parts.append(f"Stats - STR:{stats.strength} CHA:{stats.charisma} INT:{stats.intelligence} Gold:{stats.wealth}")
    if player.inventory:
        parts.append(f"Inventory: {', '.join(player.inventory)}")
    parts.append(f"Reputation - Local:{player.reputation_local} Global:{player.reputation_global}")

    # Current location
    loc = world.get_location(player.location)
    if loc:
        parts.append(f"\nCurrent location: {loc.name} - {loc.description}")
        if loc.connected_to:
            parts.append(f"Exits: {', '.join(loc.connected_to)}")
        if loc.items_available:
            parts.append(f"Items here: {', '.join(loc.items_available)}")

    # NPCs at location
    npcs_here = session.get_npcs_at_location(player.location)
    if npcs_here:
        parts.append("\nNPCs present:")
        for npc in npcs_here:
            rel = npc.relationships.get("player", 0)
            rel_str = f"(relationship: {rel:+d})" if rel != 0 else ""
            parts.append(f"  {npc.name} ({npc.role}) - {', '.join(npc.personality)} {rel_str}")

    # Active quests
    active_quests = session.get_active_quests()
    if active_quests:
        parts.append("\nActive quests:")
        for quest in active_quests:
            parts.append(f"  {quest.title}: {quest.description}")

    # Mid-term summary
    mid_summary = get_mid_term_summary(session)
    if mid_summary:
        parts.append(f"\nStory so far: {mid_summary}")

    # Recent events (short-term)
    recent = get_short_term_events(session)
    if recent:
        parts.append("\nRecent events:")
        for event in recent[-5:]:
            parts.append(f"  - {event.event}")

    return "\n".join(parts)


def build_npc_context(session: GameSession, npc_name: str) -> str:
    """Build context focused on a specific NPC for dialogue generation."""
    npc = session.get_npc(npc_name)
    if not npc:
        return ""

    parts = []
    parts.append(f"You are {npc.name}, a {npc.role}.")
    parts.append(f"Personality: {', '.join(npc.personality)}")
    parts.append(f"Goals: {', '.join(npc.goals)}")

    rel = npc.relationships.get("player", 0)
    if rel > 20:
        parts.append("You are friendly with the player.")
    elif rel < -20:
        parts.append("You distrust the player.")
    else:
        parts.append("You are neutral toward the player.")

    if npc.inventory:
        parts.append(f"Your inventory: {', '.join(npc.inventory)}")

    parts.append(f"\nWorld: {session.world.name}")
    parts.append(f"Location: {npc.location}")

    # NPC autonomy rules
    parts.append("\nRULES:")
    parts.append("- You NEVER accept unfair deals")
    parts.append("- You prioritize your own goals and self-interest")
    parts.append("- You act according to your personality traits")
    parts.append("- You cannot be convinced to act against your nature by simple requests")

    return "\n".join(parts)
