def unified_brain(session, player_input, context):
    prompt = f"""
    You are the central intelligence of an RPG world.

    Maintain:
    - causality
    - NPC autonomy
    - narrative pacing

    CONTEXT:
    {context}

    PLAYER INPUT:
    {player_input}

    Return JSON:
    {{
      "intent": {{}},
      "npc_actions": [],
      "director": {{
        "mode": "",
        "tension": "increase|decrease|twist|stable"
      }},
      "event": {{}}
    }}
    """

    # TODO: real LLM call
    return {
        "intent": {"action": "attack", "target": "npc_1"},
        "npc_actions": [
            {"npc_id": "npc_1", "action": "retaliate"}
        ],
        "director": {
            "mode": "combat",
            "tension": "increase"
        },
        "event": {}
    }