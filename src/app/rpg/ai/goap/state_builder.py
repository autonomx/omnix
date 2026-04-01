"""GOAP State Builder — converts NPC memory + beliefs into world state.

This module is the critical bridge between:
- Memory system (experience, facts, relationships)
- GOAP planner (perception-driven decision making)

The key insight: NPCs act on PERCEPTION, not truth.
Facts stored in memory become beliefs, which influence world state.

Spatial awareness: Distance to targets is computed and injected
into the world state for range-based decision making.
"""

from rpg.spatial import euclidean_distance


def inject_beliefs_into_state(npc, state):
    """Convert memory + beliefs into GOAP world state.

    This is what makes NPCs ACT based on perception, not truth.
    Beliefs derived from memory facts and relationships are injected
    into the world state, affecting planning decisions.

    Args:
        npc: The NPC whose beliefs are being converted.
        state: The current world state dict (will be mutated).

    Returns:
        The updated world state dict with belief-derived entries.
    """
    # Handle both dict-based memory and object-based memory
    if isinstance(npc.memory, dict):
        facts = npc.memory.get("facts", [])
        relationships = npc.memory.get("relationships", {})
    else:
        # If memory is a list of events, extract facts from them
        facts = []
        relationships = npc.relationships if hasattr(npc, 'relationships') else {}
        for event in npc.memory:
            if isinstance(event, dict):
                facts.append(event)

    # Process fact-based beliefs
    for belief in facts:
        text = ""
        target = None

        if isinstance(belief, dict):
            text = belief.get("text", belief.get("type", "")).lower()
            target = belief.get("target") or belief.get("source")
        elif isinstance(belief, str):
            text = belief.lower()

        if not text:
            continue

        # Threat beliefs
        if "dangerous" in text or "threat" in text or "attack" in text:
            if target:
                state[f"threat_{target}"] = True

        # Ally beliefs
        if "ally" in text or "friend" in text or "helped" in text:
            if target:
                state[f"ally_{target}"] = True

        # Hostile beliefs
        if "hostile" in text or "enemy" in text or "killed" in text:
            if target:
                state[f"hostile_{target}"] = True

    # Relationship-derived beliefs
    for other_id, rel in relationships.items():
        score = rel.get("score", 0) if isinstance(rel, dict) else 0

        if score < -5:
            state[f"hostile_{other_id}"] = True
        elif score < -8:
            state[f"enemy_{other_id}"] = True
        elif score > 5:
            state[f"friendly_{other_id}"] = True
        elif score > 8:
            state[f"ally_{other_id}"] = True

    return state


def build_world_state(npc, session):
    """Build complete GOAP world state from NPC perception.

    Combines:
    1. Raw simulation state (HP, position, etc.)
    2. Emotional state (anger, fear, etc.)
    3. Memory-derived beliefs (facts, relationships)
    4. Spatial information (distance to targets)

    Args:
        npc: The NPC whose world state is being built.
        session: The current game session.

    Returns:
        Dict representing the NPC's perceived world state.
    """
    # Base simulation state
    state = {
        "hp_low": npc.hp < 30,
        "has_target": npc.emotional_state.get("top_threat") is not None,
    }

    # Add target-specific info with SPATIAL AWARENESS
    target_id = npc.emotional_state.get("top_threat")
    if target_id:
        state["target_id"] = target_id
        state["enemy_visible"] = True
        
        # Compute distance to target
        target_npc = _get_entity(session, target_id)
        if target_npc:
            dist = euclidean_distance(npc.position, target_npc.position)
            state["target_distance"] = dist
            state["target_in_range"] = dist <= 2.5  # Attack range threshold

    # Emotional state influences
    anger = npc.emotional_state.get("anger", 0)
    fear = npc.emotional_state.get("fear", 0)

    if anger > 1.5:
        state["high_anger"] = True
    if fear > 1.5:
        state["high_fear"] = True

    # Inject beliefs from memory (the critical missing link)
    state = inject_beliefs_into_state(npc, state)

    # Inject narrative pressure from story director
    if hasattr(session, 'story_director'):
        pressure = session.story_director.get_narrative_pressure(npc.id)
        if pressure["aggression"] > 0.3:
            state["story_aggressive"] = True
        if pressure["caution"] > 0.3:
            state["story_cautious"] = True
        if pressure["urgency"] > 0.3:
            state["story_urgent"] = True

    # Faction-based defaults
    if hasattr(npc, 'faction'):
        state["faction"] = npc.faction

    return state


def _get_entity(session, entity_id):
    """Get an entity by ID from the session.
    
    Args:
        session: The current game session.
        entity_id: The entity ID to look up.
        
    Returns:
        The entity (NPC or player) or None if not found.
    """
    # Check NPCs
    for npc in session.npcs:
        if npc.id == entity_id:
            return npc
    
    # Check player
    if hasattr(session, 'player') and session.player:
        if session.player.id == entity_id:
            return session.player
    
    return None


def select_goal(npc, session=None):
    """Select NPC goal based on state, relationships, survival needs, and story arcs.

    Goals are prioritized in this order:
    1. SURVIVAL (when HP is low)
    2. MANDATED GOALS from Story Director (arcs in tension/climax)
    3. Story arc influence (revenge arcs, narrative pressure)
    4. Multi-dimensional emotion-driven goals
    5. Revenge (against hostile entities)
    6. Protection/Assistance (for allies)
    7. Exploration (default idle behavior)

    Args:
        npc: The NPC selecting a goal.
        session: Optional session for story director access.

    Returns:
        Dict representing the selected goal with type and optional target.
    """
    relationships = npc.relationships if hasattr(npc, 'relationships') else {}

    # Fallback to memory relationships if available
    if isinstance(npc.memory, dict) and not relationships:
        relationships = npc.memory.get("relationships", {})

    # Survival priority (highest)
    if npc.hp < 25:
        return {"type": "survive"}

    # Extreme danger — flee even if not critically low
    if npc.hp < 50:
        hostile_count = sum(
            1 for rel in relationships.values()
            if isinstance(rel, dict) and rel.get("score", 0) < -5
        )
        if hostile_count > 0:
            return {"type": "survive"}

    # 🔥 MANDATED GOALS — Story Director forces behavior (tension/climax arcs)
    if session and hasattr(session, 'story_director'):
        mandated = session.story_director.get_mandated_goals(npc.id)
        if mandated:
            return mandated

    # Multi-dimensional emotion-driven goals
    emotions = npc.emotional_state if hasattr(npc, 'emotional_state') else {}
    fear = emotions.get("fear", 0)
    loyalty_score = emotions.get("loyalty", 0)
    top_threat = emotions.get("top_threat")

    if fear > 1.5 and npc.hp < 40:
        return {"type": "flee"}
    if loyalty_score > 0.7:
        return {
            "type": "protect_ally",
            "target": next(iter(relationships.keys()), None)
        }

    # Story arc influence — NPCs influenced by active story arcs
    if session and hasattr(session, 'story_director'):
        arcs = session.story_director.get_arcs_for_entity(npc.id)
        for arc in arcs:
            if arc.type == "revenge" and arc.target:
                # If NPC is victim in revenge arc, pursue killer
                if arc.originator == npc.id:
                    return {
                        "type": "attack_target",
                        "target": arc.target,
                        "reason": "revenge_arc"
                    }

    # Story narrative pressure can influence aggression
    if session and hasattr(session, 'story_director'):
        pressure = session.story_director.get_narrative_pressure(npc.id)
        if pressure["aggression"] > 0.5:
            # High story aggression — look for targets
            if top_threat:
                return {
                    "type": "attack_target",
                    "target": top_threat,
                    "reason": "story_pressure"
                }

    # Revenge goal — attack those with strong negative relationships
    for other_id, rel in relationships.items():
        score = rel.get("score", 0) if isinstance(rel, dict) else 0
        if score < -8:
            return {
                "type": "attack_target",
                "target": other_id
            }

    # Hostile belief from memory
    if isinstance(npc.memory, dict):
        facts = npc.memory.get("facts", [])
        for belief in facts:
            if isinstance(belief, dict):
                text = belief.get("text", "").lower()
                target = belief.get("target")
                if target and ("enemy" in text or "hostile" in text):
                    return {
                        "type": "attack_target",
                        "target": target
                    }

    # Social goal — assist allies
    for other_id, rel in relationships.items():
        score = rel.get("score", 0) if isinstance(rel, dict) else 0
        if score > 8:
            return {
                "type": "assist_target",
                "target": other_id
            }

    # Default: explore/wander
    return {"type": "explore"}
