"""Grounding Block Builder — structured simulation truth for scene generation.

The grounding block is the source of truth for scene generation.
It contains ONLY simulation facts — no LLM hallucination allowed.

Architecture:
    SIMULATION → GROUNDING BLOCK → SCENE RENDERER

Grounding includes:
    - Entity states (HP, position, active status)
    - Intentions (current goals, actions)
    - Emotional states (anger, fear, trust levels)
    - Relationships (trust, anger, fear between entities)
    - Memories (recent relevant memories per entity)
    - Distances between entities
    - Visibility / line of sight
    - Recent events
"""

from app.rpg.spatial import euclidean_distance
from app.rpg.memory.relationships import (
    get_all_relationship_summaries,
)


def _has_line_of_sight(pos_a, pos_b, session):
    """Check if two positions have line of sight.
    
    Currently checks if positions are within visible range.
    Can be extended with raycasting for obstacles.
    
    Args:
        pos_a: First position.
        pos_b: Second position.
        session: Game session.
        
    Returns:
        True if line of sight exists.
    """
    dist = euclidean_distance(pos_a, pos_b)
    # Line of sight range - can see within 10 units
    return dist <= 10.0


def _build_entity_grounding(entity_id, entity) -> dict:
    """Build comprehensive entity grounding block with all state info.
    
    Includes:
    - Basic state (hp, position, active)
    - Current goal/intent
    - Emotional state
    - Belief system (hostile targets, trusted allies, dangerous entities)
    - Relationship summaries
    - Recent relevant memories
    
    Args:
        entity_id: The entity's ID string
        entity: The entity object (NPC or player)
        
    Returns:
        Dict with complete entity grounding data
    """
    base = {
        "id": entity_id,
        "position": entity.position if hasattr(entity, 'position') else (0, 0),
        "active": entity.hp > 0 if hasattr(entity, 'hp') else True
    }
    
    # HP (if entity has it)
    if hasattr(entity, 'hp'):
        base["hp"] = entity.hp
    
    # Current goal/intent (memory-based intent grounding)
    if hasattr(entity, 'current_goal') and entity.current_goal:
        base["intent"] = entity.current_goal
    elif hasattr(entity, 'goals') and entity.goals:
        base["intent"] = entity.goals[0] if entity.goals else None
    else:
        base["intent"] = None
    
    # Emotional state
    if hasattr(entity, 'emotional_state'):
        base["emotional_state"] = dict(entity.emotional_state)
    else:
        base["emotional_state"] = {}
    
    # BELIEF SYSTEM INJECTION (CRITICAL for LLM grounding)
    # Inject belief-derived state into grounding so LLM knows:
    # - Who the NPC considers hostile
    # - Who the NPC trusts
    # - What entities are observed as dangerous
    # - Overall world threat assessment
    if hasattr(entity, 'belief_system'):
        bs = entity.belief_system
        base["beliefs"] = {
            "summary": bs.get_summary(),
            "hostile_targets": bs.get("hostile_targets", [])[:2],  # Top 2
            "trusted_allies": bs.get("trusted_allies", [])[:2],    # Top 2
            "dangerous_entities": bs.get("dangerous_entities", [])[:2],  # Observed danger
            "world_threat_level": bs.get("world_threat_level", "low"),
            "hostility_intensity": bs.get("hostility_intensity", {}),
            "trust_intensity": bs.get("trust_intensity", {}),
        }
    else:
        base["beliefs"] = {
            "summary": "No beliefs formed yet",
            "hostile_targets": [],
            "trusted_allies": [],
            "dangerous_entities": [],
            "world_threat_level": "low",
            "hostility_intensity": {},
            "trust_intensity": {},
        }
    
    # Relationship summaries (what I think about others)
    if hasattr(entity, 'relationships') or (isinstance(getattr(entity, 'memory', {}), dict) and 'relationships' in getattr(entity, 'memory', {})):
        rel_summaries = get_all_relationship_summaries(entity)
        base["relationships"] = rel_summaries
    else:
        base["relationships"] = []
    
    # Recent memories (top 3 most important for context)
    if hasattr(entity, 'memory') and entity.memory:
        memories = entity.memory.get("events", []) if isinstance(entity.memory, dict) else entity.memory
        # Get most recent 3 memories with meaning
        recent = memories[-3:] if len(memories) >= 3 else memories
        base["memories"] = [
            {"meaning": m.get("meaning", ""), "type": m.get("type", ""), "timestamp": m.get("timestamp", m.get("tick", 0))}
            for m in recent
        ]
    else:
        base["memories"] = []
    
    return base


def build_grounding_block(session, events, npc_actions):
    """Build grounding block from current simulation state.

    This captures the exact state of the world at this tick,
    providing hard constraints for scene generation.

    Enhanced with:
    - Entity intent (current goals)
    - Entity emotional state
    - Entity relationships
    - Entity recent memories
    - Memory-based relationship data
    - DESIGN SPEC ITEM 10: Story Director state (phase, tension, arc)

    Args:
        session: The current game session.
        events: List of events that occurred this tick.
        npc_actions: List of NPC actions decided this tick.

    Returns:
        Dict containing entities, relationships, distances,
        visibility, intentions, memories, events, and story state.
    """
    entities = []
    npc_positions = {}
    npc_map = {}

    # Collect NPCs
    all_npcs = []
    if hasattr(session, 'player') and session.player:
        all_npcs.append(("player", session.player))
    for npc in session.npcs:
        all_npcs.append((npc.id, npc))

    # Build enhanced entity list with intent, emotion, relationships, memories
    for entity_id, entity in all_npcs:
        entity_grounding = _build_entity_grounding(entity_id, entity)
        entities.append(entity_grounding)
        npc_positions[entity_id] = entity.position if hasattr(entity, 'position') else (0, 0)
        npc_map[entity_id] = entity

    # Build relationships between entities (combines model relationships + memory-based)
    relationships = []
    for eid_a, ent_a in all_npcs:
        for eid_b, ent_b in all_npcs:
            if eid_a == eid_b:
                continue
            
            # First try memory-based relationship system (new)
            if hasattr(ent_a, 'memory') and isinstance(ent_a.memory, dict):
                rels = ent_a.memory.get("relationships", {})
                if eid_b in rels:
                    rel = rels[eid_b]
                    trust = rel.get("trust", 0)
                    anger = rel.get("anger", 0)
                    
                    attitude = "neutral"
                    if anger > 0.7:
                        attitude = "hostile"
                    elif trust > 0.7:
                        attitude = "friendly"
                    if anger > 0.9:
                        attitude = "enemy"
                    elif trust > 0.9:
                        attitude = "ally"
                    
                    relationships.append({
                        "source": eid_a,
                        "target": eid_b,
                        "attitude": attitude,
                        "trust": trust,
                        "anger": anger,
                        "fear": rel.get("fear", 0),
                    })
                    continue
            
            # Fall back to legacy relationship model
            if hasattr(ent_a, 'relationships') and eid_b in ent_a.relationships:
                rel = ent_a.relationships[eid_b]
                score = rel.get("score", 0) if isinstance(rel, dict) else 0
                
                attitude = "neutral"
                if score > 5:
                    attitude = "friendly"
                elif score < -5:
                    attitude = "hostile"
                if score > 8:
                    attitude = "ally"
                elif score < -8:
                    attitude = "enemy"
                    
                relationships.append({
                    "source": eid_a,
                    "target": eid_b,
                    "attitude": attitude,
                    "score": score,
                })

    # Build distance matrix
    distances = []
    for eid_a in npc_positions:
        pos_a = npc_positions[eid_a]
        for eid_b in npc_positions:
            if eid_a >= eid_b:
                continue
            pos_b = npc_positions[eid_b]
            distances.append({
                "from": eid_a,
                "to": eid_b,
                "distance": euclidean_distance(pos_a, pos_b),
            })

    # Build visibility map
    visibility = []
    for eid_a, ent_a in all_npcs:
        vis = []
        for eid_b, ent_b in all_npcs:
            if eid_a == eid_b:
                continue
            pos_a = npc_positions.get(eid_a, (0, 0))
            pos_b = npc_positions.get(eid_b, (0, 0))
            if _has_line_of_sight(pos_a, pos_b, session):
                vis.append(eid_b)
        visibility.append({
            "entity": eid_a,
            "can_see": vis,
        })

    # Build intentions from last actions
    intentions = []
    for action in npc_actions:
        intentions.append({
            "entity": action.get("npc_id"),
            "action": action.get("action"),
            "target": action.get("target_id"),
            "plan": action.get("plan", []),
        })

    grounding = {
        "entities": entities,
        "relationships": relationships,
        "distances": distances,
        "visibility": visibility,
        "intentions": intentions,
        "events": events,
        "npc_actions": npc_actions,
        "actions": npc_actions,  # Alias for compatibility
        "time": session.world.time if hasattr(session, 'world') else 0,
    }
    
    # DESIGN SPEC ITEM 10: LLM Grounding Integration - Fix #6
    # Injects comprehensive story state from StoryDirector for scene generation.
    # Uses per-entity story state which includes active arcs, local tension, etc.
    # This allows the LLM to follow tone:
    #   - intro -> calm, exploratory
    #   - tension -> cautious, reactive
    #   - climax -> decisive, emotional
    if hasattr(session, 'story_director') and session.story_director:
        # Use enhanced per-entity story state (Fix #6: includes active_arcs)
        global_story = session.story_director.get_story_state()
        grounding["story"] = global_story
        grounding["story_global"] = global_story
    else:
        grounding["story"] = {
            "phase": "intro",
            "tension": 0.0,
            "local_tension": 0.0,
            "arc": None,
            "tension_level": "calm",
            "active_arcs": [],
            "arc_count": 0,
        }
        grounding["story_global"] = grounding["story"]
    
    return grounding
