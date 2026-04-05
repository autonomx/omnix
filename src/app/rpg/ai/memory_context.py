"""Memory Context for NPC AI - Builds structured memory context for decision making.

Provides:
- build_memory_context: Retrieves and formats memories for AI/LLM prompts
- format_memories: Converts memory entries to LLM-friendly narrative strings
- summarize_relationships: Extracts relationship patterns with sentiment analysis
- get_beliefs: Retrieves NPC's formed beliefs from semantic memory
"""

import math

from app.rpg.memory.retrieval import retrieve_memories


def build_memory_context(npc, current_event: dict, session) -> str:
    """Returns structured memory context for AI / LLM.
    
    Retrieves the most relevant memories based on the current event context,
    then formats them into a readable string suitable for LLM prompts.
    
    Includes:
    - Beliefs (formed from reflection)
    - Recent relevant memories
    - Relationship summaries
    """
    memories = retrieve_memories(
        npc,
        context=current_event,
        current_time=session.world.time,
        k=5,
        mode="planning"
    )

    memory_text = format_memories(memories)
    relationship_text = summarize_relationships(npc, session)
    belief_text = format_beliefs(get_beliefs(npc))

    return f"""
Beliefs:
{belief_text}

Recent relevant memories:
{memory_text}

Relationships:
{relationship_text}
"""


def format_memories(memories: list) -> str:
    """Format memories into LLM-friendly narrative.
    
    Uses meaning field when available, falls back to timestamped format.
    Adds importance signals for high-importance memories.
    """
    if not memories:
        return "No relevant memories."

    lines = []

    for m in memories:
        meaning = m.get("meaning")

        if meaning:
            line = f"- {meaning}"
        else:
            line = (
                f"- At time {m.get('timestamp', m.get('tick', 0))}, "
                f"{m.get('source', 'unknown')} {m.get('type', 'unknown')} {m.get('target', 'unknown')}"
            )

        # Add importance signal
        if m.get("importance", 1.0) >= 3:
            line += " (very important)"

        lines.append(line)

    return "\n".join(lines)


def summarize_relationships(npc, session) -> str:
    """Extract relationship patterns with sentiment-based tone descriptions.
    
    Returns formatted string suitable for LLM consumption.
    """
    memories = npc.memory.get("events", []) if isinstance(npc.memory, dict) else npc.memory
    current_time = session.world.time
    
    # Track raw sentiment and interaction counts
    raw_data = {}
    
    for m in memories:
        source = m.get("source", m.get("actor"))
        target = m.get("target")
        mem_type = m.get("type")
        importance = m.get("importance", 1.0)
        timestamp = m.get("timestamp", m.get("tick", 0))
        
        def update(entity_id, score_delta, ts):
            if entity_id not in raw_data:
                raw_data[entity_id] = {"score": 0.0, "count": 0, "last_updated": ts}
            raw_data[entity_id]["score"] += score_delta
            raw_data[entity_id]["count"] += 1
            raw_data[entity_id]["last_updated"] = max(
                raw_data[entity_id]["last_updated"], ts
            )
        
        if source and source != npc.id:
            if mem_type == "heal":
                update(source, importance, timestamp)
            elif mem_type in ("damage", "death"):
                if target == npc.id:
                    update(source, -importance * 2, timestamp)
        
        if target and target != npc.id:
            if mem_type in ("damage", "death") and source == npc.id:
                update(target, -importance, timestamp)
    
    # Apply time decay and format
    lines = []
    for entity_id, data in raw_data.items():
        age = current_time - data["last_updated"]
        decay = math.exp(-age / 50) if age > 0 else 1.0
        sentiment = data["score"] * decay

        if sentiment > 2:
            tone = "trust"
        elif sentiment < -2:
            tone = "hostility"
        else:
            tone = "neutral"

        lines.append(f"- I feel {tone} toward {entity_id}")

    return "\n".join(lines) if lines else "No significant relationships."


def get_beliefs(npc) -> list:
    """Retrieve NPC's formed beliefs from semantic memory."""
    facts = npc.memory.get("facts", []) if isinstance(npc.memory, dict) else []
    return facts[-3:]  # Most recent 3 beliefs


def format_beliefs(beliefs: list) -> str:
    """Format beliefs for LLM consumption."""
    if not beliefs:
        return "No formed beliefs yet."

    lines = []
    for b in beliefs:
        lines.append(f"- {b.get('text', str(b))}")

    return "\n".join(lines)