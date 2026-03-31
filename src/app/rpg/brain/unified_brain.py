from rpg.ai.npc_planner import decide as npc_decide
from rpg.memory.retrieval import retrieve


def unified_brain(session, player_input, context):
    enriched_npcs = []
    for npc in session.npcs:
        memory = retrieve(npc, {"type": "damage"})
        enriched_npcs.append({
            "id": npc.id,
            "memory": memory
        })

    prompt = f"""
    You are the central intelligence of an RPG world.

    Maintain:
    - causality
    - NPC autonomy
    - narrative pacing

    CONTEXT:
    {context}

    NPC MEMORY:
    {enriched_npcs}

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
    npc_actions = []
    for npc in session.npcs:
        if npc.is_active:
            npc_actions.append({
                "npc_id": npc.id,
                **npc_decide(npc, session)
            })

    return {
        "intent": {"action": "attack", "target": "npc_1"},
        "npc_actions": npc_actions,
        "director": {
            "mode": "combat",
            "tension": "increase"
        },
        "event": {}
    }