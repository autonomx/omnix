"""
Intent Translator for the RPG Mode Upgrade.

Converts natural language player input into structured RPG intents with action types,
targets, styles, and emotional tones for the simulation pipeline.
"""

import logging
from typing import Dict

from app.rpg.agents import _call_llm, _parse_json_response

logger = logging.getLogger(__name__)


def translate_intent(player_input: str) -> Dict[str, str]:
    """
    Convert player input into structured RPG intent.

    Analyzes natural language to determine:
    - Action type (attack, talk, explore, investigate, etc.)
    - Target of the action
    - Style (aggressive, careful, stealthy)
    - Emotional tone

    Returns structured intent data.
    """
    prompt = f"""Convert player input into structured RPG intent.

Player input: "{player_input}"

Include:
- action: the type of action (attack, talk, explore, investigate, use_item, move, etc.)
- target: what or who the action is directed at (person, place, object, or empty)
- style: how the action is performed (aggressive, careful, stealthy, diplomatic, forceful, etc.)
- emotion: the emotional tone (anger, fear, confidence, curiosity, determination, etc.)

Return JSON:
{{
  "action": "action_type",
  "target": "target_name",
  "style": "action_style",
  "emotion": "emotional_tone"
}}"""

    result = _call_llm("You are an intent translator for RPG games.", prompt)
    parsed = _parse_json_response(result)

    if not parsed:
        logger.warning("Intent translation failed, using fallback")
        # Simple fallback based on keywords
        input_lower = player_input.lower()
        if any(word in input_lower for word in ['attack', 'fight', 'hit', 'strike']):
            action = 'attack'
            emotion = 'anger'
            style = 'aggressive'
        elif any(word in input_lower for word in ['talk', 'speak', 'ask', 'say']):
            action = 'talk'
            emotion = 'confidence'
            style = 'diplomatic'
        elif any(word in input_lower for word in ['explore', 'look', 'search', 'investigate']):
            action = 'investigate'
            emotion = 'curiosity'
            style = 'careful'
        else:
            action = 'other'
            emotion = 'neutral'
            style = 'normal'

        # Extract target (simple noun extraction)
        words = player_input.split()
        target = ""
        for word in words:
            if word.lower() not in ['i', 'the', 'a', 'an', 'to', 'at', 'with', 'in', 'on', 'and', 'or']:
                target = word
                break

        return {
            "action": action,
            "target": target,
            "style": style,
            "emotion": emotion
        }

    return parsed