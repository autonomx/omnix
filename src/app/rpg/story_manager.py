"""
Story Manager for the RPG Mode Upgrade.

Replaces the old progress += 0.1 system with LLM-driven story arc management.
Handles progression, escalation, resolution, and creation of new story arcs.
"""

import logging
from typing import Any, Dict, List

from app.rpg.agents import _call_llm, _parse_json_response

logger = logging.getLogger(__name__)


def update_story_arcs(session) -> List[Dict[str, Any]]:
    """
    Update all active story arcs based on current session state.

    Uses LLM to determine arc progression, escalation, resolution, and new arcs.
    Returns a list of new pending consequences from arc updates.
    """
    if not session.story_arcs:
        return []

    active_arcs = [arc for arc in session.story_arcs if arc.status == "active"]

    if not active_arcs:
        return []

    # Build context
    context = {
        "active_arcs": [
            {
                "title": arc.title,
                "description": arc.description,
                "progress": arc.progress,
                "tension_level": arc.tension_level,
                "key_events": arc.key_events[-3:],  # Last 3 events
                "status": arc.status
            } for arc in active_arcs
        ],
        "recent_events": [h.event for h in session.history[-5:]],
        "world_state": f"{session.world.name} - tension: {session.narrative_tension}",
        "player_location": session.player.location,
        "turn_count": session.turn_count
    }

    prompt = f"""Given the current story arcs and recent events, update story arcs.

Active arcs: {context['active_arcs']}
Recent events: {context['recent_events']}
World tension: {context['world_state']}
Player location: {context['player_location']}
Turn count: {context['turn_count']}

For each active arc, decide:
- progress: how much progress (0.0 to 1.0)
- escalation: should tension increase? (yes/no)
- resolution: should this arc resolve? (yes/no and how)
- new_arcs: should new arcs be created? (list new arc ideas)

Return JSON with arc updates:
{{
  "arc_updates": [
    {{
      "arc_title": "Arc Title",
      "progress": 0.0,
      "tension_change": 0.0,
      "resolution": "none|partial|complete",
      "resolution_description": "how it resolves",
      "new_key_event": "new event to add"
    }}
  ],
  "new_arcs": [
    {{
      "title": "New Arc Title",
      "description": "Arc description",
      "initial_tension": 0.0,
      "triggers": ["trigger conditions"]
    }}
  ],
  "consequences": [
    {{
      "description": "Consequence narrative",
      "importance": 0.7,
      "trigger_turn": {context['turn_count']} + 2
    }}
  ]
}}"""

    result = _call_llm("You are a story arc manager for RPG games.", prompt)
    parsed = _parse_json_response(result)

    consequences = []

    if parsed:
        # Apply arc updates
        for update in parsed.get("arc_updates", []):
            arc_title = update.get("arc_title")
            for arc in session.story_arcs:
                if arc.title == arc_title:
                    arc.progress = update.get("progress", arc.progress)
                    arc.tension_level += update.get("tension_change", 0.0)
                    resolution = update.get("resolution", "none")

                    if resolution != "none":
                        arc.status = "resolved" if resolution == "complete" else "completed"
                        if update.get("resolution_description"):
                            arc.key_events.append(f"Resolution: {update['resolution_description']}")

                    if update.get("new_key_event"):
                        arc.key_events.append(update["new_key_event"])

                    break

        # Create new arcs
        for new_arc_data in parsed.get("new_arcs", []):
            # This would need to create actual StoryArc objects
            # For now, we'll just log and add consequences
            logger.info("New story arc proposed: %s", new_arc_data.get("title"))

        # Add consequences
        for cons in parsed.get("consequences", []):
            from app.rpg.models import PendingConsequence
            consequence = PendingConsequence(
                source_event="story_arc_update",
                narrative=cons.get("description", "Story consequence occurs"),
                importance=cons.get("importance", 0.7),
                trigger_turn=cons.get("trigger_turn", session.turn_count + 2),
                type="story"
            )
            consequences.append(consequence)

    else:
        logger.warning("Story arc update failed, using fallback")
        # Fallback: slight progress on all arcs
        for arc in active_arcs:
            arc.progress = min(1.0, arc.progress + 0.05)

    return consequences