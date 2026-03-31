"""
Narrative Director for the RPG Mode Upgrade.

Interprets player input narratively, manages pacing, injects events, and orchestrates
scene composition for cinematic storytelling.
"""

import logging
from typing import Dict, Any

from app.rpg.agents import _call_llm, _parse_json_response

logger = logging.getLogger(__name__)


class NarrativeDirector:
    """Manages narrative flow and scene orchestration."""

    def decide_next_step(self, session, player_input: str) -> Dict[str, Any]:
        """
        Decide the next narrative step based on player input and current session state.

        Interprets player input narratively, decides pacing, injects events,
        selects active NPCs, and chooses scene focus.

        Returns a dict with narrative decisions.
        """
        # Build context from session
        context = self._build_narrative_context(session)

        prompt = f"""You are a narrative director for an RPG.

Given:
- World state: {context['world_summary']}
- Active arcs: {context['active_arcs']}
- Player input: "{player_input}"
- Current tension: {context['tension']}
- Recent events: {context['recent_events']}

Decide:

1. What is the narrative intent? (action, exploration, dialogue, combat, etc.)
2. What should happen next? (scene description)
3. Which NPCs are involved? (list of NPC IDs)
4. Should tension increase, decrease, or twist? (increase/decrease/twist/stable)
5. Should a new event occur? (yes/no and what type)

Return JSON:
{{
  "intent": "narrative intent",
  "scene_focus": "what the scene focuses on",
  "npc_ids": ["npc1", "npc2"],
  "event": "event description or empty",
  "tension": "increase|decrease|twist|stable"
}}"""

        result = _call_llm("You are a narrative director for RPG games.", prompt)
        parsed = _parse_json_response(result)

        if not parsed:
            logger.warning("Narrative director failed, using fallback")
            return {
                "intent": "action",
                "scene_focus": "player action",
                "npc_ids": [],
                "event": "",
                "tension": "stable"
            }

        return parsed

    def _build_narrative_context(self, session) -> Dict[str, Any]:
        """Build context for narrative decision making."""
        recent_events = [h.event for h in session.history[-5:]]

        active_arcs = []
        for arc in session.story_arcs:
            if arc.status == "active":
                active_arcs.append(f"{arc.title}: {arc.description}")

        world_summary = f"{session.world.name} - {session.world.description}"

        return {
            "world_summary": world_summary,
            "active_arcs": active_arcs,
            "tension": session.narrative_tension,
            "recent_events": recent_events,
            "player_location": session.player.location,
            "turn_count": session.turn_count
        }