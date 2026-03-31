from rpg.models import SceneOutput


def generate_scene(session, director, result, event, npc_actions):
    event_summary = summarize_events(result["events"])

    active_npcs = [n.id for n in session.npcs if n.is_active]

    prompt = f"""
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
    Active NPCs: {active_npcs}
    Time: {session.world.time}

    EVENTS:
    {event_summary}

    NPC ACTIONS:
    {npc_actions}
    """

    # mock (TODO: integrate with LLM for actual generation)
    return SceneOutput(
        location="battlefield",
        scene_type=director["mode"],
        tone="tense",
        tension=0.7,
        narration=" | ".join(event_summary),
        characters=[],
        choices=[]
    )


def summarize_events(events):
    lines = []
    for e in events:
        if e["type"] == "damage":
            lines.append(f"{e['source']} hits {e['target']} for {e['amount']}")
        if e["type"] == "death":
            lines.append(f"{e['target']} dies")
    return lines