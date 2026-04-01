"""Story module — Dynamic narrative control.

Exports the Story Director system for managing story arcs,
narrative tension, arc phases, and forced narrative events.

Design spec: rpg-design.txt

Key exports:
    StoryDirector: Main director class with adjust_goal() for goal shaping
    get_story_prompt: Helper for LLM scene generation prompts
"""

from rpg.story.director import (
    StoryDirector,
    StoryArc,
    ARC_PHASES,
    select_events_for_scene,
)


def get_story_prompt(grounding_dict) -> str:
    """Generate story prompt text for LLM scene generation.
    
    Uses the 'story' key from grounding block to generate
    narrative tone instructions for the LLM.
    
    Args:
        grounding_dict: Grounding block from build_grounding_block()
        
    Returns:
        Formatted story state prompt for scene generation.
    """
    story = grounding_dict.get("story", {})
    if not story:
        return ""
    
    phase = story.get("phase", "intro")
    tension = story.get("tension", 0.0)
    arc = story.get("arc", "none")
    
    # Tone mapping per design spec
    tone_map = {
        "intro": "calm, exploratory, setting the scene",
        "build": "growing suspicion, subtle tension",
        "tension": "cautious, reactive, on edge",
        "climax": "decisive, emotional, high stakes",
    }
    
    tone = tone_map.get(phase, "neutral")
    
    return f"Story State: Phase={phase}, Tension={tension:.2f}, Arc={arc}. Follow tone: {tone}."


__all__ = [
    "StoryDirector",
    "StoryArc", 
    "ARC_PHASES",
    "select_events_for_scene",
    "get_story_prompt",
]
