"""GOAP State Builder — converts NPC memory + beliefs into world state.

This module is the critical bridge between:
- Memory system (experience, facts, relationships)
- GOAP planner (perception-driven decision making)

The key insight: NPCs act on PERCEPTION, not truth.
Facts stored in memory become beliefs, which influence world state.

Spatial awareness: Distance to targets is computed and injected
into the world state for range-based decision making.
"""

from app.rpg.spatial import euclidean_distance


def inject_beliefs_into_state(npc, state):
    """Convert memory + beliefs into GOAP world state.

    This is what makes NPCs ACT based on perception, not truth.
    Beliefs derived from memory facts and relationships are injected
    into the world state, affecting planning decisions.

    Priority order for belief injection:
    1. BeliefSystem-derived beliefs (new, most comprehensive)
    2. Memory fact-based beliefs (existing)
    3. Relationship-derived beliefs (existing)

    Args:
        npc: The NPC whose beliefs are being converted.
        state: The current world state dict (will be mutated).

    Returns:
        The updated world state dict with belief-derived entries.
    """
    # 🔥 BeliefSystem-derived beliefs (new priority layer)
    if hasattr(npc, 'belief_system') and npc.belief_system:
        bs = npc.belief_system

        # Hostile targets from belief system
        hostile = bs.get("hostile_targets", [])
        for target_id in hostile:
            state[f"hostile_{target_id}"] = True
            state[f"threat_{target_id}"] = True

        # Trusted allies from belief system
        allies = bs.get("trusted_allies", [])
        for target_id in allies:
            state[f"ally_{target_id}"] = True
            state[f"friendly_{target_id}"] = True

        # Subjugated entities (entities NPC has harmed)
        subjugated = bs.get("subjugated_targets", [])
        for target_id in subjugated:
            state[f"subjugated_{target_id}"] = True

        # World threat level influences overall state
        threat_level = bs.get("world_threat_level", "low")
        if threat_level in ("high", "very_high"):
            state["world_dangerous"] = True
            state["threat_level"] = threat_level

        # Hostility intensity for targeting priority
        intensity = bs.get("hostility_intensity", {})
        for target_id, score in intensity.items():
            state[f"hostility_intensity_{target_id}"] = score

        # Trust intensity for alliance priority
        trust_intensity = bs.get("trust_intensity", {})
        for target_id, score in trust_intensity.items():
            state[f"trust_intensity_{target_id}"] = score

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

    # Process fact-based beliefs (legacy, kept for backward compatibility)
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

    # Relationship-derived beliefs (legacy, kept for backward compatibility)
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
    2. BELIEF-DRIVEN GOALS from BeliefSystem (emergent hostility/alliances)
    3. MANDATED GOALS from Story Director (arcs in tension/climax)
    4. Story arc influence (revenge arcs, narrative pressure)
    5. Multi-dimensional emotion-driven goals
    6. Revenge (against hostile entities)
    7. Protection/Assistance (for allies)
    8. Exploration (default idle behavior)
    9. DESIGN SPEC: adjust_goal() from StoryDirector applies final bias

    Args:
        npc: The NPC selecting a goal.
        session: Optional session for story director access.

    Returns:
        Dict representing the selected goal with type, optional target, and priority.
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

    # 🔥 BELIEF-DRIVEN GOALS — Emergent from memory patterns (new priority layer)
    if hasattr(npc, 'belief_system') and npc.belief_system:
        bs = npc.belief_system

        # Hostile targets from belief system — emergent grudges
        hostile = bs.get("hostile_targets", [])
        if hostile:
            # Use best target scoring instead of just first
            from app.rpg.memory.belief_system import pick_best_target
            best_target = pick_best_target(npc, hostile)
            target = best_target if best_target else hostile[0]
            return {
                "type": "attack_target",
                "target": target,
                "reason": "belief_hostility",
                "force": min(1.0, bs.get("hostility_intensity", {}).get(target, 1) * 0.3)
            }

        # Trusted allies — protect those who helped us
        allies = bs.get("trusted_allies", [])
        if allies and npc.hp > 60:
            return {
                "type": "assist_target",
                "target": allies[0],
                "reason": "belief_alliance"
            }

        # Dangerous entities observed — be cautious
        dangerous = bs.get("dangerous_entities", [])
        if dangerous and npc.hp < 70:
            return {"type": "survive"}

        # High world threat — be cautious
        if bs.get("world_threat_level") in ("high", "very_high"):
            if npc.hp < 70:
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


def select_goal_with_story_bias(npc, session, recent_events=None):
    """Select goal and apply StoryDirector.adjust_goal() for final story bias.
    
    This implements design spec item 7: Hook Into GOAP.
    After selecting a goal based on beliefs, mandates, and emotions,
    the Story Director applies arc-based biasing and pacing.
    
    Usage (replace existing select_goal calls):
        goal = select_goal_with_story_bias(npc, session, events)
    
    Args:
        npc: The NPC selecting a goal.
        session: The game session with story_director.
        recent_events: Optional list of recent events for tension update.
        
    Returns:
        Goal dict with priority adjusted by StoryDirector.
    """
    # First, select goal using existing logic
    goal = select_goal(npc, session)
    
    # Add default priority and name for adjust_goal
    goal.setdefault("priority", 1.0)
    goal.setdefault("name", goal.get("type", "unknown"))
    
    # Apply StoryDirector bias if available
    if session and hasattr(session, 'story_director'):
        director = session.story_director
        context = {"recent_events": recent_events or []}
        goal = director.adjust_goal(npc, goal, context)
    
    return goal
