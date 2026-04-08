"""Memory Retrieval System - Talemate-style ranked, filtered, decayed memories.

Provides:
- compute_recency_decay: exponential decay based on time delta
- compute_relevance: lightweight relevance scoring (no embeddings)
- score_memory: combined scoring with weights
- retrieve_memories: top-k memory retrieval for NPCs
- retrieve_with_filters: structured query retrieval with type/target/time filters

Memory Types:
- episodic: "what happened" - event memories
- semantic: "what is true" - beliefs and facts
- relationship: "how I feel about X" - relationship state
"""

import math
from typing import Any, Dict, List, Optional

# Memory type constants
MEMORY_TYPES = {
    "episodic": "Event-based memory of what happened",
    "semantic": "Belief-based memory of what is true",
    "relationship": "State memory of relationships with entities",
}

# Retrieval mode weight profiles
RETRIEVAL_WEIGHTS = {
    "general": {"relevance": 0.5, "importance": 0.3, "recency": 0.2},
    "combat": {"relevance": 0.3, "importance": 0.4, "recency": 0.3},
    "social": {"relevance": 0.6, "importance": 0.2, "recency": 0.2},
    "planning": {"relevance": 0.3, "importance": 0.5, "recency": 0.2},
    "query_threat": {"relevance": 0.4, "importance": 0.4, "recency": 0.2},
    "query_emotional": {"relevance": 0.5, "importance": 0.3, "recency": 0.2},
    "query_conflict": {"relevance": 0.4, "importance": 0.35, "recency": 0.25},
    "query_matters_now": {"relevance": 0.6, "importance": 0.25, "recency": 0.15},
}


def compute_recency_decay(timestamp: int, current_time: int, half_life: int = 50) -> float:
    """
    Exponential decay:
    newer = closer to 1.0
    older = approaches 0
    """
    delta = current_time - timestamp
    return math.exp(-delta / half_life)


def compute_relevance(memory: Dict[str, Any], context: Dict[str, Any]) -> float:
    """
    Weighted relevance scoring with source/target distinction.
    
    Prioritizes:
    - Target matching (who was affected) - highest weight
    - Source matching (who caused it) - medium weight
    - Type matching (same event type) - lower weight
    
    This ensures "player killed my ally" is more relevant than
    "player healed me" when context involves the player as threat.
    """
    score = 0.0

    # Source matching (who caused the event)
    if memory.get("source") == context.get("source"):
        score += 1.0

    # Target matching (who was affected) - highest weight
    if memory.get("target") == context.get("target"):
        score += 1.5

    # Type matching (same event category)
    mem_type = memory.get("type", memory.get("event_type", ""))
    if mem_type == context.get("type"):
        score += 0.5

    return score


def compute_weighted_importance(memory: Dict[str, Any]) -> float:
    """Compute emotion-weighted importance with negative memory bias.
    
    Negative events (damage, death) are boosted to ensure NPCs:
    - Hold grudges against attackers
    - Fear entities that have harmed them
    - Prioritize threats over neutral interactions
    """
    importance = memory.get("importance", 1.0)
    mem_type = memory.get("type", memory.get("event_type", ""))
    memory_class = memory.get("memory_type", "episodic")

    # Boost negative memories for realistic behavior
    if mem_type == "damage":
        importance *= 1.5
    
    if mem_type == "death":
        importance *= 2.0
    
    # Relationship memory significance
    if memory_class == "relationship":
        importance *= memory.get("emotional_intensity", 1.0)
    
    # Semantic (belief) memories have base high importance
    if memory_class == "semantic":
        importance *= 1.3
    
    # Emotional impact multiplier (if available)
    emotional_impact = memory.get("emotional_impact", 0)
    importance *= (1 + abs(emotional_impact) * 0.2)
    
    return importance


def score_memory(memory: Dict[str, Any], context: Dict[str, Any], current_time: int) -> float:
    """Score a memory entry based on relevance, importance, and recency."""
    relevance = compute_relevance(memory, context)
    importance = compute_weighted_importance(memory)
    recency = compute_recency_decay(memory.get("timestamp", memory.get("tick", 0)), current_time)

    return (
        relevance * 0.5 +
        importance * 0.3 +
        recency * 0.2
    )


def _get_memories_for_npc(npc) -> List[Dict[str, Any]]:
    """Extract memory list from NPC, supporting both dict and list formats."""
    if isinstance(npc.memory, dict):
        return npc.memory.get("events", [])
    return npc.memory


def _filter_memories(
    memories: List[Dict[str, Any]],
    target: Optional[str] = None,
    event_type: Optional[str] = None,
    memory_type: Optional[str] = None,
    time_window: Optional[str] = None,
    current_time: int = 0,
) -> List[Dict[str, Any]]:
    """Filter memories by structured query criteria.
    
    Args:
        memories: List of memory dicts to filter
        target: Filter by target entity ID
        event_type: Filter by event type (damage, death, etc.)
        memory_type: Filter by memory type (episodic, semantic, relationship)
        time_window: "recent" (last 20 ticks), "older" (beyond 20 ticks), or None
        current_time: Current world time for time window calculation
        
    Returns:
        Filtered list of memories
    """
    result = []
    
    for mem in memories:
        # Target filter (checks both target and source)
        if target:
            mem_target = mem.get("target", "")
            mem_source = mem.get("source", "")
            mem_actor = mem.get("actor", "")
            if target not in (mem_target, mem_source, mem_actor):
                continue
        
        # Event type filter
        if event_type:
            mem_type = mem.get("type", mem.get("event_type", ""))
            if mem_type != event_type:
                continue
        
        # Memory class filter
        if memory_type:
            if mem.get("memory_type", "episodic") != memory_type:
                continue
        
        # Time window filter
        if time_window:
            timestamp = mem.get("timestamp", mem.get("tick", 0))
            age = current_time - timestamp
            if time_window == "recent" and age > 20:
                continue
            if time_window == "older" and age <= 20:
                continue
        
        result.append(mem)
    
    return result


def retrieve_with_filters(
    npc,
    target: Optional[str] = None,
    intent: Optional[str] = None,
    time_window: Optional[str] = None,
    current_time: int = 0,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve memories using structured query filters.
    
    This is the upgraded retrieval system that replaces vague queries like
    retrieve("who hurt me") with precise structured queries.
    
    Args:
        npc: The NPC whose memories to retrieve
        target: Target entity to filter by (e.g., npc.emotional_state.get("top_threat"))
        intent: Intent context affecting event type filter:
            - "combat": filters for damage/death events
            - "social": filters for dialogue/heal events
            - None: no event type filter
        time_window: "recent", "older", or None
        current_time: Current world time
        k: Number of memories to return
        
    Returns:
        Top-k filtered and scored memories
    """
    # Map intent to event type filter
    event_type = None
    if intent == "combat":
        event_type = None  # Will boost damage type but not filter
    elif intent == "social":
        event_type = None
    
    # Get all memories and apply filters
    all_memories = _get_memories_for_npc(npc)
    filtered = _filter_memories(
        all_memories,
        target=target,
        event_type=event_type,
        time_window=time_window,
        current_time=current_time,
    )
    
    # Score and rank filtered memories
    weights = RETRIEVAL_WEIGHTS.get(
        f"query_{intent}" if intent else "general",
        RETRIEVAL_WEIGHTS["general"]
    )
    
    scored = []
    for mem in filtered:
        relevance = compute_relevance(mem, {"target": target, "type": event_type})
        importance = compute_weighted_importance(mem)
        recency = compute_recency_decay(mem.get("timestamp", mem.get("tick", 0)), current_time)
        
        # Boost combat-relevant memories when intent is combat
        if intent == "combat" and mem.get("type") in ("damage", "death"):
            importance *= 1.5
        
        s = (
            relevance * weights["relevance"] +
            importance * weights["importance"] +
            recency * weights["recency"]
        )
        scored.append((s, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:k]]


def retrieve_memories(
    npc,
    context: Dict[str, Any],
    current_time: int,
    k: int = 5,
    mode: str = "general"
) -> List[Dict[str, Any]]:
    """Retrieve top-k most relevant memories for an NPC given context.
    
    Args:
        npc: The NPC whose memories to retrieve
        context: The current event context for relevance scoring
        current_time: Current world time for recency calculation
        k: Number of memories to return
        mode: Retrieval mode affecting weights:
            - "general": balanced retrieval (default)
            - "combat": prioritizes recent + hostile memories
            - "social": prioritizes dialogue + emotional memories
            - "planning": prioritizes high-importance strategic memories
            - "query_threat": retrieve threat-related memories
            - "query_emotional": retrieve emotion-related memories
            - "query_conflict": retrieve conflict-related memories
            - "query_matters_now": retrieve most currently relevant
    
    Returns:
        List of top-k memory dicts, sorted by relevance score
    """
    weights = RETRIEVAL_WEIGHTS.get(mode, RETRIEVAL_WEIGHTS["general"])
    memories = _get_memories_for_npc(npc)

    scored = []
    for mem in memories:
        relevance = compute_relevance(mem, context)
        importance = compute_weighted_importance(mem)
        recency = compute_recency_decay(mem.get("timestamp", mem.get("tick", 0)), current_time)
        
        s = (
            relevance * weights["relevance"] +
            importance * weights["importance"] +
            recency * weights["recency"]
        )
        scored.append((s, mem))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [m for _, m in scored[:k]]
