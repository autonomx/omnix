"""
Event Injection System for the RPG Mode Upgrade.

Injects dynamic events like ambushes, betrayals, discoveries, and environmental
changes to maintain narrative tension and surprise.
"""

import logging
import random
from typing import Dict, Any, Optional

from app.rpg.agents import _call_llm, _parse_json_response

logger = logging.getLogger(__name__)


def inject_event(session, director_output: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Inject a dynamic event based on narrative direction and session state.

    Returns event data if an event should be injected, None otherwise.
    """
    tension = session.narrative_tension
    turn_count = session.turn_count
    player_location = session.player.location

    # Don't inject events too frequently
    if turn_count % 3 != 0:
        return None

    # Higher chance with higher tension
    inject_chance = min(0.3, tension * 0.5)
    if random.random() > inject_chance:
        return None

    # Build context for event generation
    context = {
        "tension": tension,
        "location": player_location,
        "active_arcs": [arc.title for arc in session.story_arcs if arc.status == "active"],
        "recent_events": [h.event for h in session.history[-3:]],
        "npcs_present": [npc.name for npc in session.npcs if npc.location == player_location],
        "director_intent": director_output.get("intent", "unknown")
    }

    prompt = f"""Generate a dynamic event to inject into the RPG narrative.

Context:
- Current tension: {context['tension']}
- Location: {context['location']}
- Active story arcs: {context['active_arcs']}
- Recent events: {context['recent_events']}
- NPCs present: {context['npcs_present']}
- Narrative intent: {context['director_intent']}

Choose an appropriate event type:
- ambush: sudden attack or threat
- betrayal: someone turns against the player
- discovery: finding something important
- environmental_change: weather, terrain, or location change
- alliance: someone offers help
- mystery: unexplained occurrence

Return JSON:
{{
  "event_type": "event_type",
  "description": "brief event description",
  "narrative": "how it appears in the scene",
  "consequences": ["list of mechanical effects"],
  "importance": 0.0
}}"""

    result = _call_llm("You are an event injection engine for RPGs.", prompt)
    parsed = _parse_json_response(result)

    if not parsed:
        logger.warning("Event injection failed")
        return None

    event_type = parsed.get("event_type", "discovery")
    description = parsed.get("description", "Something unexpected happens")
    narrative = parsed.get("narrative", description)
    consequences = parsed.get("consequences", [])
    importance = parsed.get("importance", 0.5)

    logger.info("Injected event: %s (%s)", event_type, description)

    return {
        "type": event_type,
        "description": description,
        "narrative": narrative,
        "consequences": consequences,
        "importance": importance
    }