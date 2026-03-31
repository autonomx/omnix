from rpg.models import SceneOutput

def generate_scene(session, director, result, event, npc_actions):
    event_summary = summarize_events(result["events"])

    prompt = f"""
    Generate a cinematic RPG scene.

    MUST FOLLOW:
    - reflect ALL events
    - show consequences
    - include NPC reactions
    - DO NOT invent new events
    - DO NOT contradict events
    - EVERY line must be traceable to EVENTS or NPC ACTIONS

    EVENTS:
    {event_summary}

    NPC ACTIONS:
    {npc_actions}

    Return JSON:
    {{
      "location": "",
      "scene_type": "",
      "tone": "",
      "tension": 0.0,
      "narration": "",
      "characters": [],
      "choices": []
    }}
    """

    # mock
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