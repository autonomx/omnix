"""
Adventure Setup System for the RPG Mode Upgrade.

Handles initial world generation and adventure configuration using LLM-driven
worldbuilding to create custom worlds per session.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.rpg.agents import _call_llm, _parse_json_response

logger = logging.getLogger(__name__)


@dataclass
class AdventureConfig:
    """Configuration for adventure setup."""
    genre: str
    tone: str
    setting: str
    world_rules: str
    player_role: str
    themes: List[str]


def generate_world(config: AdventureConfig) -> Dict[str, Any]:
    """
    Generate a complete world using LLM-driven worldbuilding.

    Returns a dictionary containing:
    - World description
    - 3-5 factions
    - 5 important NPCs
    - Starting location
    - Initial conflict
    - Hidden tensions
    """
    prompt = f"""You are a worldbuilding engine.

Using the following configuration:

Genre: {config.genre}
Tone: {config.tone}
Setting: {config.setting}
Rules: {config.world_rules}
Player Role: {config.player_role}
Themes: {', '.join(config.themes)}

Generate:

1. World description
2. 3–5 factions
3. 5 important NPCs
4. Starting location
5. Initial conflict
6. Hidden tensions

Return JSON with the following structure:
{{
  "description": "World description",
  "factions": [
    {{
      "name": "Faction name",
      "description": "Faction description",
      "goals": "Faction goals",
      "power_level": "low/medium/high"
    }}
  ],
  "npcs": [
    {{
      "name": "NPC name",
      "role": "NPC role",
      "personality": "Personality traits",
      "relationship_to_player": "initial relationship",
      "goals": "NPC goals"
    }}
  ],
  "starting_location": "Location name",
  "initial_conflict": "Initial conflict description",
  "hidden_tensions": "Hidden tensions description"
}}"""

    result = _call_llm("You are a worldbuilding engine that creates detailed RPG worlds.", prompt)
    parsed = _parse_json_response(result)

    if not parsed:
        logger.warning("World generation failed, using fallback")
        return {
            "description": f"A {config.genre} world with {config.tone} tone.",
            "factions": [
                {
                    "name": "Default Faction",
                    "description": "A faction in this world.",
                    "goals": "Maintain stability",
                    "power_level": "medium"
                }
            ],
            "npcs": [
                {
                    "name": "Default NPC",
                    "role": "Helper",
                    "personality": "Friendly",
                    "relationship_to_player": "neutral",
                    "goals": "Assist adventurers"
                }
            ],
            "starting_location": "Village",
            "initial_conflict": "A mysterious threat looms.",
            "hidden_tensions": "Ancient secrets wait to be uncovered."
        }

    return parsed