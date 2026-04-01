from rpg.models import SceneOutput
from rpg.scene_graph import build_scene_graph


def generate_scene(session, director, result, event, npc_actions):
    event_summary = summarize_events(result["events"])

    # Build structured scene graph for world state
    graph = build_scene_graph(session)

    active_npcs = [n.id for n in session.npcs if n.is_active]

    # Hybrid rendering: simulation is truth, LLM is flavor layer
    base_scene = f"""
    TIME: {graph['time']}
    ACTIVE NPCs: {active_npcs}

    ENTITIES:
    {graph['entities']}

    EVENTS:
    {event_summary}

    NPC ACTIONS:
    {npc_actions}
    """

    # TODO: integrate with LLM for actual generation
    # LLM enhances but cannot override the simulation truth
    _llm_prompt = f"""
    Generate a structured cinematic scene.

    STRICT RULES:
    - ONLY describe what is in EVENTS
    - DO NOT invent outcomes
    - ALL consequences must match state
    - deaths MUST be reflected

    STRUCTURE:
    1. Setup
    2. Action
    3. Reaction
    4. Aftermath

    SETUP CONTEXT:
    {base_scene}
    """

    # merge_scene keeps simulation events as the ground truth
    final_narration = _merge_scene(base_scene, event_summary)

    return SceneOutput(
        location="battlefield",
        scene_type=director["mode"],
        tone="tense",
        tension=0.7,
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
    lines = []
    for e in events:
        if e["type"] == "damage":
            lines.append(f'{e["source"]} hit {e["target"]} for {e["amount"]}')
        elif e["type"] == "death":
            lines.append(f'{e["target"]} died')
    return "\n".join(lines)