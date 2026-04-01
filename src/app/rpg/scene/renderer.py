"""Deterministic Scene Renderer — zero-hallucination scene generation.

This module replaces free-text LLM generation with structured rendering.
The simulation is truth; the renderer converts simulation events into
text descriptions. An optional LLM layer can add cinematic flavor
without changing facts.

Architecture:
    EVENTS → RENDERER → TEXT (truth preserved)
    TEXT → LLM (optional flavor only, constrained)
"""


def render_scene_deterministic(grounding):
    """Convert simulation grounding into text without LLM.

    This is the ZERO hallucination renderer. It only uses facts
    from the grounding block, never invents new events.

    Args:
        grounding: Dict containing entities, events, actions, and time.

    Returns:
        String containing the deterministic scene description.
    """
    lines = []

    # Time header
    time_info = grounding.get("time", 0)
    lines.append(f"=== TICK {time_info} ===")
    lines.append("")

    # Entity status
    entities = grounding.get("entities", [])
    if entities:
        lines.append("STATUS:")
        for entity in entities:
            entity_id = entity.get("id", "unknown")
            hp = entity.get("hp", 0)
            position = entity.get("position", (0, 0))
            active = entity.get("active", True) if "active" in entity else hp > 0

            if active and hp > 0:
                lines.append(f"  {entity_id}: HP={hp} at {position}")
            else:
                lines.append(f"  {entity_id}: DEFEATED")
        lines.append("")

    # Events
    events = grounding.get("events", [])
    if events:
        lines.append("ACTIONS:")
        for event in events:
            event_type = event.get("type", "unknown")
            source = event.get("source", event.get("actor", "unknown"))
            target = event.get("target", "unknown")

            if event_type == "damage":
                amount = event.get("amount", 0)
                lines.append(
                    f"  {source} attacks {target} for {amount} damage."
                )
            elif event_type == "death":
                lines.append(f"  {target} has died.")
            elif event_type == "heal":
                amount = event.get("amount", 0)
                lines.append(f"  {source} heals {target} for {amount} HP.")
            elif event_type == "move":
                dest = event.get("destination", event.get("position", "somewhere"))
                lines.append(f"  {source} moves to {dest}.")
            else:
                lines.append(f"  {source} performs {event_type} on {target}.")
        lines.append("")

    # NPC Actions
    actions = grounding.get("npc_actions", []) or grounding.get("actions", [])
    if actions:
        lines.append("INTENTIONS:")
        for action in actions:
            npc_id = action.get("npc_id", action.get("actor", "unknown"))
            action_type = action.get("action", "unknown")
            target = action.get("target", "")

            if target:
                lines.append(f"  {npc_id} intends to {action_type} {target}")
            else:
                lines.append(f"  {npc_id} intends to {action_type}")
        lines.append("")

    return "\n".join(lines)


def render_event_summary(events):
    """Generate brief one-line summary of events.

    Args:
        events: List of event dicts.

    Returns:
        String summary of key events.
    """
    if not events:
        return "Nothing happened."

    summaries = []
    for event in events:
        event_type = event.get("type", "unknown")
        source = event.get("source", event.get("actor", "unknown"))
        target = event.get("target", "unknown")

        if event_type == "damage":
            amount = event.get("amount", 0)
            summaries.append(f"{source} hits {target} ({amount} dmg)")
        elif event_type == "death":
            summaries.append(f"{target} dies")
        elif event_type == "heal":
            amount = event.get("amount", 0)
            summaries.append(f"{source} heals {target}")

    return "; ".join(summaries)


def render_with_llm_flavor(session, grounding, deterministic_scene):
    """Render scene with optional LLM flavor layer.

    The LLM can ONLY add descriptive language, atmosphere, and
    emotional tone. It CANNOT change facts, add events, or alter
    outcomes.

    Args:
        session: Game session with LLM access.
        grounding: The grounding block (source of truth).
        deterministic_scene: The deterministic scene text.

    Returns:
        The LLM-flavored scene, or deterministic scene if LLM fails.
    """
    if not hasattr(session, 'llm_generate') or session.llm_generate is None:
        return deterministic_scene

    prompt = f"""
You are a cinematic scene writer. Your job is to add atmospheric detail
to a scene WITHOUT changing any facts.

HARD CONSTRAINTS (MUST FOLLOW):
- DO NOT add new characters
- DO NOT add new events
- DO NOT change outcomes
- DO NOT alter HP values
- Only enhance descriptions, atmosphere, and emotional tone

SCENE FACTS (these are immutable):
{deterministic_scene}

Rewrite this scene with cinematic detail while preserving ALL facts.
Keep the same structure and information, just make it more vivid.
"""

    try:
        llm_result = session.llm_generate(prompt)
        if llm_result and llm_result.strip():
            return llm_result.strip()
    except Exception:
        pass

    # Fallback to deterministic scene
    return deterministic_scene