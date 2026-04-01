"""Memory Consolidation System - Prevents memory explosion and creates semantic beliefs.

This system:
- Merges repeated events into single semantic memories ("X attacked me 5 times" → "X is dangerous")
- Converts episodic memories into semantic beliefs
- Prunes low-importance old memories
- Maintains memory performance and long-term coherence

Call consolidate_memories(npc) periodically (e.g., every 10 ticks) to keep memory manageable.
"""

from typing import List, Dict, Any, Tuple
from collections import defaultdict


def _get_memory_key(mem: Dict[str, Any]) -> Tuple[str, str, str]:
    """Create a hashable key for grouping similar memories.
    
    Groups memories by (event_type, source, target) to find repetitions.
    """
    return (
        mem.get("type", mem.get("event_type", "unknown")),
        mem.get("source", mem.get("actor", "unknown")),
        mem.get("target", "unknown"),
    )


def merge_repeated_events(
    memories: List[Dict[str, Any]],
    merge_threshold: int = 3,
    current_time: int = 0,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Merge repeated similar events into consolidated memories.
    
    When the same type of event happens multiple times between the same
    entities, merge them into a single memory with count and timestamp range.
    
    Args:
        memories: List of memory dicts to consolidate
        merge_threshold: Minimum repetitions before merging (default: 3)
        current_time: Current world time for timestamp
        
    Returns:
        Tuple of (remaining_unmerged_memories, merged_consolidated_memories)
    """
    # Group memories by key
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    ungrouped: List[Dict[str, Any]] = []
    
    for mem in memories:
        # Skip semantic and relationship memories - only merge episodic events
        if mem.get("memory_type") in ("semantic", "relationship"):
            ungrouped.append(mem)
            continue
            
        key = _get_memory_key(mem)
        groups[key].append(mem)
    
    merged: List[Dict[str, Any]] = []
    remaining: List[Dict[str, Any]] = []
    
    for key, group_memories in groups.items():
        if len(group_memories) >= merge_threshold:
            # Merge into consolidated memory
            event_type, source, target = key
            timestamps = [m.get("timestamp", m.get("tick", 0)) for m in group_memories]
            max_importance = max((m.get("importance", 1.0) for m in group_memories), default=1.0)
            
            consolidated = {
                "memory_type": "episodic_consolidated",
                "type": event_type,
                "source": source,
                "target": target,
                "count": len(group_memories),
                "first_occurrence": min(timestamps),
                "last_occurrence": max(timestamps),
                "timestamp": current_time,
                "importance": min(max_importance * 1.2, 5.0),  # Boost for pattern significance
                "meaning": f"{source} has {event_type} {target} {len(group_memories)} times",
            }
            merged.append(consolidated)
        else:
            # Not enough repetitions - keep individual memories
            remaining.extend(group_memories)
    
    remaining.extend(ungrouped)
    return remaining, merged


def convert_to_semantic(
    memories: List[Dict[str, Any]],
    current_time: int = 0,
) -> List[Dict[str, Any]]:
    """Convert patterns in episodic memories into semantic beliefs.
    
    Analyzes memories for patterns and generates semantic "fact" memories
    like "X is dangerous", "X can be trusted", etc.
    
    Args:
        memories: List of memory dicts to analyze
        current_time: Current world time for timestamp
        
    Returns:
        List of new semantic belief memories (can be empty if no patterns found)
    """
    semantic_memories: List[Dict[str, Any]] = []
    
    # Analyze damage patterns - who is dangerous?
    damage_counts: Dict[str, int] = defaultdict(int)
    damage_sources: Dict[str, set] = defaultdict(set)
    
    for mem in memories:
        mem_type = mem.get("type", mem.get("event_type", ""))
        source = mem.get("source", mem.get("actor", ""))
        target = mem.get("target", "")
        
        if mem_type == "damage":
            damage_counts[target] += 1
            if source:
                damage_sources[target].add(source)
        
        # Track consolidated memories for pattern detection
        if mem.get("memory_type") == "episodic_consolidated":
            count = mem.get("count", 1)
            damage_counts[target] += count
            if source:
                damage_sources[target].add(source)
    
    # Generate semantic beliefs from patterns
    for entity_id, count in damage_counts.items():
        # Entity has been damaged many times - may be vulnerable
        if count >= 5:
            semantic_memories.append({
                "memory_type": "semantic",
                "type": "belief",
                "source": entity_id,
                "target": entity_id,
                "text": "I have been attacked many times - the world is dangerous",
                "timestamp": current_time,
                "importance": 2.5,
            })
        
        # Entities that have caused significant damage are threats
        for source in damage_sources.get(entity_id, set()):
            source_damage = sum(
                mem.get("count", 1) for mem in memories
                if mem.get("memory_type") == "episodic_consolidated"
                and mem.get("source") == source
                and mem.get("target") == entity_id
            )
            
            if source_damage >= 3:
                semantic_memories.append({
                    "memory_type": "semantic",
                    "type": "belief",
                    "source": entity_id,
                    "target": source,
                    "text": f"{source} is dangerous and has harmed me multiple times",
                    "timestamp": current_time,
                    "importance": 3.5,
                })
    
    return semantic_memories


def _prune_low_importance(
    memories: List[Dict[str, Any]],
    max_memories: int = 100,
    min_importance: float = 0.5,
    current_time: int = 0,
) -> List[Dict[str, Any]]:
    """Prune low-importance and old memories to prevent explosion.
    
    Args:
        memories: List of memory dicts to prune
        max_memories: Maximum memories to keep
        min_importance: Minimum importance threshold for old memories
        current_time: Current world time for age calculation
        
    Returns:
        Pruned list of memories
    """
    if len(memories) <= max_memories:
        return memories
    
    # Always keep high-importance and recent memories
    important = [m for m in memories if m.get("importance", 1.0) >= 2.0]
    recent_cutoff = current_time - 50
    recent = [m for m in memories if m.get("timestamp", m.get("tick", 0)) >= recent_cutoff]
    
    # Combine and sort by importance
    keep = {id(m): m for m in important + recent}
    
    if len(keep) >= max_memories:
        # Take top by importance
        sorted_keep = sorted(keep.values(), key=lambda m: m.get("importance", 0), reverse=True)
        return sorted_keep[:max_memories]
    
    # Fill remaining slots with medium-importance memories
    remaining = [m for m in memories if id(m) not in keep and m.get("importance", 1.0) >= min_importance]
    remaining.sort(key=lambda m: m.get("importance", 0), reverse=True)
    
    result = list(keep.values())
    remaining_slots = max_memories - len(result)
    result.extend(remaining[:remaining_slots])
    
    return result


def consolidate_memories(
    npc,
    current_time: int = 0,
    merge_threshold: int = 3,
    max_memories: int = 100,
) -> Dict[str, Any]:
    """Run full memory consolidation for an NPC.
    
    This should be called periodically (e.g., every 10 ticks) to:
    1. Merge repeated episodic events
    2. Convert patterns to semantic beliefs
    3. Prune low-importance old memories
    
    Args:
        npc: The NPC to consolidate memories for
        current_time: Current world time (defaults to npc.session.world.time if available)
        merge_threshold: Minimum repetitions before merging events
        max_memories: Maximum memories to keep after consolidation
        
    Returns:
        Dict with consolidation stats: {"merged": N, "semantic_created": N, "pruned": N}
    """
    # Get current time from session if not provided
    if current_time == 0 and hasattr(npc, 'session') and npc.session:
        current_time = getattr(npc.session.world, 'time', 0)
    
    # Get current memories
    if isinstance(npc.memory, dict):
        memories = npc.memory.get("events", [])
    else:
        memories = list(npc.memory)
    
    if not memories:
        return {"merged": 0, "semantic_created": 0, "pruned": 0}
    
    original_count = len(memories)
    
    # Step 1: Merge repeated events
    remaining, merged = merge_repeated_events(memories, merge_threshold, current_time)
    
    # Step 2: Convert patterns to semantic beliefs
    new_semantic = convert_to_semantic(remaining + merged, current_time)
    
    # Step 3: Combine all memories
    all_memories = remaining + merged + new_semantic
    
    # Step 4: Prune to max capacity
    pruned = _prune_low_importance(all_memories, max_memories, current_time=current_time)
    
    # Update NPC memory
    if isinstance(npc.memory, dict):
        npc.memory["events"] = pruned
    else:
        npc.memory = pruned
    
    return {
        "original": original_count,
        "merged": len(merged),
        "semantic_created": len(new_semantic),
        "pruned": original_count + len(merged) + len(new_semantic) - len(pruned),
        "final": len(pruned),
    }