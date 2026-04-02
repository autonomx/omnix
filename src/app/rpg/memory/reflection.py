"""Reflection System - Converts memories into high-level beliefs.

This is what turns:
  memory → intelligence

NPCs convert experiences into beliefs like:
  "The player is dangerous"
  "This area is safe"
  "I can trust the healer"
"""

from app.rpg.memory.retrieval import retrieve_memories


def reflect(npc, session, llm_generate) -> str:
    """
    Generate high-level beliefs from recent memories.
    
    Args:
        npc: The NPC to reflect for
        session: The game session (provides world.time)
        llm_generate: A function that takes a prompt and returns LLM response
    
    Returns:
        The generated belief statements (also stored in npc.memory["facts"])
    """
    context = {
        "type": "reflection",
        "source": npc.id,
    }

    memories = retrieve_memories(
        npc,
        context=context,
        current_time=session.world.time,
        k=10,
        mode="planning"
    )

    if not memories:
        return ""

    memory_text = "\n".join([
        m.get("meaning", str(m.get("data", m)))
        for m in memories
    ])

    prompt = f"""
You are {npc.name}.

Based on your memories:

{memory_text}

What do you believe about the world, other characters, or threats?

Respond with 1-3 short belief statements.
Each statement should be on its own line.
Be concise and specific.
"""

    result = llm_generate(prompt)

    store_reflection(npc, result, session)

    return result


def store_reflection(npc, text: str, session):
    """
    Store reflections as semantic memory (facts/beliefs).
    
    Each reflection is stored with high importance to ensure it persists
    and influences future decision-making.
    """
    if "facts" not in npc.memory:
        npc.memory["facts"] = []

    # Split into individual beliefs and store each
    beliefs = [line.strip() for line in text.strip().split("\n") if line.strip()]

    for belief in beliefs:
        npc.memory["facts"].append({
            "text": belief,
            "timestamp": session.world.time,
            "importance": 3.0,
            "type": "belief"
        })


def reflect_all(session, llm_generate):
    """
    Run reflection for all NPCs in the session.
    
    Call this periodically (e.g., every 5 ticks) to ensure
    NPCs continuously form beliefs from their experiences.
    """
    for npc in session.npcs:
        if npc.is_active:
            reflect(npc, session, llm_generate)