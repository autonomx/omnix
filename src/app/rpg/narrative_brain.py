from rpg.narrative_context import build_context


def narrative_brain(session, player_input, context):
    prompt = f"""
    You are the narrative brain of an RPG.

    Maintain:
    - coherence
    - pacing
    - character consistency
    - cause and effect

    === CONTEXT ===
    World: {context['world_summary']}
    Active Arcs: {context['active_arcs']}
    NPC States: {context['npc_states']}
    Recent Events: {context['recent_events']}
    Player Profile: {context['player_profile']}
    Tone: {context['tone']}
    Tension Level: {context['tension']}

    === PLAYER INPUT ===
    {player_input}

    === TASK ===

    Return JSON:

    {{
      "intent": {{
        "action": "",
        "target": "",
        "style": "",
        "emotion": ""
      }},
      "director": {{
        "mode": "dialogue|combat|exploration|cinematic",
        "scene_focus": "",
        "npc_ids": [],
        "tension": "increase|decrease|twist|stable"
      }},
      "arc_updates": [],
      "event": {{
        "type": "",
        "cause": "",
        "description": ""
      }}
    }}
    """

    # Mock LLM response for simulation
    return {
        "intent": {
            "action": "explore",
            "target": "",
            "style": "curious",
            "emotion": "neutral"
        },
        "director": {
            "mode": "exploration",
            "scene_focus": "current_location",
            "npc_ids": [],
            "tension": "stable"
        },
        "arc_updates": [],
        "event": {
            "type": "none",
            "cause": "",
            "description": ""
        }
    }