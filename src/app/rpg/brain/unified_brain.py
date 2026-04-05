from app.rpg.ai.npc_planner import decide as npc_decide
from app.rpg.memory.retrieval import retrieve_memories


def interpret_player_input(player_input: str) -> dict:
    """PATCH 6: Classify player input into structured intent.
    
    Instead of hardcoded outputs, this function uses a structured prompt
    that can be fed to an LLM for proper intent classification.
    
    Args:
        player_input: Raw player input text.
        
    Returns:
        Structured intent dict with type, intent, target, and tone.
    """
    # Structured LLM prompt for intent classification
    prompt = f"""
    Classify the player input into structured intent.

    Input: {player_input}

    Return JSON:
    {{
        "type": "action|dialogue",
        "intent": "...",
        "target": "...",
        "tone": "neutral|friendly|aggressive|hostile|calm"
    }}
    """
    
    # TODO: Replace with actual LLM call
    # For now, use simple heuristic classification
    input_lower = player_input.lower()
    
    intent_type = "action"
    tone = "neutral"
    
    # Detect dialogue
    if any(w in input_lower for w in ["say", "tell", "ask", "hello", "hi", "please"]):
        intent_type = "dialogue"
        
    # Detect tone
    if any(w in input_lower for w in ["attack", "kill", "fight", "die", "hurt"]):
        tone = "aggressive"
    elif any(w in input_lower for w in ["hello", "hi", "please", "help", "thank"]):
        tone = "friendly"
    elif any(w in input_lower for w in ["wait", "look", "observe", "think"]):
        tone = "calm"
        
    # Detect target
    target = None
    if "guard" in input_lower:
        target = "guard"
    elif "npc" in input_lower:
        target = "npc_1"
        
    return {
        "type": intent_type,
        "intent": player_input,
        "target": target,
        "tone": tone,
    }


def unified_brain(session, player_input, context):
    """Central intelligence of the RPG world.
    
    PATCH 6: Replace stub with structured intent classification.
    
    Maintains:
    - Causality (events follow logically)
    - NPC autonomy (NPCs act independently)
    - Narrative pacing (story flows naturally)
    
    Args:
        session: The current game session.
        player_input: Raw player input text.
        context: Context dict from build_context().
        
    Returns:
        Dict with intent, npc_actions, director info, and event.
    """
    enriched_npcs = []
    for npc in session.npcs:
        current_time = session.world.time if hasattr(session, 'world') else 0
        memory = retrieve_memories(npc, {"type": "damage"}, current_time, k=3)
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

    # PATCH 6: Use structured intent classification
    intent = interpret_player_input(player_input)
    
    # NPC actions from GOAP
    npc_actions = []
    for npc in session.npcs:
        if npc.is_active:
            npc_actions.append({
                "npc_id": npc.id,
                **npc_decide(npc, session)
            })

    return {
        "intent": intent,
        "npc_actions": npc_actions,
        "director": {
            "mode": "adaptive",
            "tension": "stable"
        },
        "event": {}
    }
