import json
import logging
from rpg.prompting.builder import build_prompt

logger = logging.getLogger(__name__)

def validate_llm_output(data: dict) -> dict:
    """Validate and sanitize LLM output with length limits and better sanitization."""
    valid_emotions = ["neutral", "angry", "happy", "fearful"]

    desc = str(data.get("description", "")).strip()
    if not desc:
        desc = "Something happens."
    if len(desc) > 200:
        desc = desc[:200] + "..."

    dialogue = str(data.get("dialogue", "")).strip()
    if len(dialogue) > 100:
        dialogue = dialogue[:100] + "..."

    emotion = data.get("emotion", "neutral")
    if emotion not in valid_emotions:
        emotion = "neutral"

    return {
        "version": 1,
        "description": desc,
        "dialogue": dialogue,
        "emotion": emotion
    }

def generate_narration(npc, action, outcome, scene, memory, llm_client=None):
    """
    Generate narration for an action.
    If llm_client is provided, use it.
    Otherwise fallback to deterministic narration.
    """

    # LLM path (optional)
    if llm_client:
        prompt = build_prompt(npc, scene, memory)

        # Retry strategy
        for _ in range(2):
            try:
                response = llm_client.generate(prompt)
                parsed = json.loads(response)
                validated = validate_llm_output(parsed)
                return validated
            except Exception as e:
                logger.warning("LLM parse failed: %s", e)
                continue

        # fallback if LLM fails after retries
        pass

    # Deterministic fallback
    description = ""
    dialogue = ""
    emotion = "neutral"

    if action.type == "attack" and action.target:
        if outcome == "critical_success":
            description = f"{npc.name} lands a devastating blow on {action.target.name}!"
            emotion = "happy"
        elif outcome == "success":
            description = f"{npc.name} hits {action.target.name}."
            emotion = "neutral"
        elif outcome == "partial_success":
            description = f"{npc.name} grazes {action.target.name}."
            emotion = "neutral"
        else:
            description = f"{npc.name} misses {action.target.name}."
            emotion = "angry"

    elif action.type == "flee":
        description = f"{npc.name} attempts to flee."
        emotion = "fearful"

    elif action.type == "scan":
        description = f"{npc.name} observes the surroundings carefully."
        emotion = "neutral"

    else:
        description = f"{npc.name} waits."
        emotion = "neutral"

    return {
        "version": 1,
        "description": description,
        "dialogue": dialogue,
        "emotion": emotion
    }