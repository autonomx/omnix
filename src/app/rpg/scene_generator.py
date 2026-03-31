"""
Scene Generator for the RPG Mode Upgrade.

Creates cinematic scenes with vivid narration, character dialogue, emotional tone,
and meaningful choices based on world state and player actions.
"""

import logging
from typing import Any, Dict, List

from app.rpg.agents import _call_llm, _parse_json_response

logger = logging.getLogger(__name__)


def generate_scene(session, director_output: Dict[str, Any], pipeline_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a cinematic RPG scene based on narrative direction and simulation results.

    Returns structured scene data with location, tone, narration, characters, and choices.
    """
    # Extract NPCs involved
    npc_ids = director_output.get("npc_ids", [])
    characters = []
    for npc_id in npc_ids:
        npc = session.get_npc(npc_id)
        if npc:
            characters.append({
                "name": npc.name,
                "role": getattr(npc, 'role', 'NPC'),
                "personality": getattr(npc, 'personality', 'Unknown'),
                "emotional_state": getattr(npc, 'emotional_state', 'neutral')
            })

    # Build context
    context = {
        "world_state": f"{session.world.name} - {session.world.description}",
        "player_action": pipeline_result.get("outcome", "Player takes action"),
        "scene_focus": director_output.get("scene_focus", "general scene"),
        "current_tension": session.narrative_tension,
        "location": session.player.location,
        "npcs_involved": characters,
        "recent_events": [h.event for h in session.history[-3:]]
    }

    prompt = f"""Generate a cinematic RPG scene.

Use:
- World state: {context['world_state']}
- Player action result: {context['player_action']}
- Scene focus: {context['scene_focus']}
- Current tension: {context['current_tension']}
- Location: {context['location']}
- NPCs involved: {context['npcs_involved']}
- Recent events: {context['recent_events']}

Include:
- Vivid narration describing the scene
- Character dialogue consistent with personalities
- Emotional tone matching the situation
- 3 meaningful choices for the player

Return JSON:
{{
  "scene": {{
    "location": "scene location",
    "tone": "atmospheric tone",
    "summary": "brief scene summary"
  }},
  "narration": "vivid narrative description",
  "characters": [
    {{
      "name": "Character Name",
      "dialogue": "What they say",
      "emotion": "emotional state",
      "action": "what they're doing"
    }}
  ],
  "choices": [
    "Choice 1",
    "Choice 2",
    "Choice 3"
  ]
}}"""

    result = _call_llm("You are a cinematic scene generator for RPG games.", prompt)
    parsed = _parse_json_response(result)

    if not parsed:
        logger.warning("Scene generation failed, using fallback")
        return {
            "scene": {
                "location": session.player.location,
                "tone": "neutral",
                "summary": "A scene unfolds"
            },
            "narration": f"You find yourself in {session.player.location}. {pipeline_result.get('outcome', 'Something happens.')}",
            "characters": [],
            "choices": [
                "Continue exploring",
                "Talk to someone",
                "Take a different action"
            ]
        }

    return parsed