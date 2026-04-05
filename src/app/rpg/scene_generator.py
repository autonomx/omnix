"""Scene Generator — deterministic rendering with optional LLM flavor.

Architecture:
    EVENTS → GROUNDING → DETERMINISTIC RENDER → LLM FLAVOR (optional)

The simulation is truth. The LLM can only add atmosphere, never change facts.
"""

from app.rpg.models import SceneOutput
from app.rpg.scene.grounding import build_grounding_block
from app.rpg.scene.renderer import render_scene_deterministic, render_with_llm_flavor
from app.rpg.scene.validator import validate_scene


def generate_scene(session, director, result, event, npc_actions):
    """Generate a scene from simulation events.

    Uses deterministic rendering to ensure zero hallucination.
    LLM flavor is optional and constrained to atmospheric detail only.

    Args:
        session: The current game session.
        director: Director state (mode, tension, etc.).
        result: Simulation result with events.
        event: The triggering event.
        npc_actions: List of NPC actions this tick.

    Returns:
        SceneOutput containing the narration.
    """
    # Build grounding block (source of truth)
    grounding = build_grounding_block(session, result.get("events", []), npc_actions)

    # Deterministic rendering — simulation is truth
    deterministic_scene = render_scene_deterministic(grounding)

    # Optional: LLM flavor layer (constrained)
    final_narration = deterministic_scene

    if hasattr(session, 'llm_generate') and session.llm_generate is not None:
        final_narration = render_with_llm_flavor(session, grounding, deterministic_scene)

    # Validate scene against grounding to prevent hallucination
    if not validate_scene(final_narration, grounding):
        final_narration = "[ERROR: Scene rejected due to hallucination]"

    return SceneOutput(
        location="battlefield",
        scene_type=director.get("mode", "action"),
        tone="tense",
        tension=director.get("tension", 0.7),
        narration=final_narration,
        characters=[],
        choices=[]
    )


def _merge_scene(base_scene, narrative):
    """Merge base simulation scene with narrative, keeping simulation as truth."""
    if narrative:
        return f"{base_scene.strip()}\n\nNARRATIVE:\n{narrative}"
    return base_scene.strip()


def summarize_events(events):
    """Summarize events for quick display."""
    lines = []
    for e in events:
        if e["type"] == "damage":
            lines.append(f'{e["source"]} hit {e["target"]} for {e["amount"]}')
        elif e["type"] == "death":
            lines.append(f'{e["target"]} died')
    return "\n".join(lines)