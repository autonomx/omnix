"""Orchestrator — Unified main loop for RPG simulation.

This module implements PATCH 3 from the RPG design specification:
"UNIFIED MAIN LOOP (CRITICAL)"

The problem: Systems run without orchestration.
The solution: A single orchestrator function that runs each turn in
the correct order: Player → Director → World → NPCs → Events → Memory → Narrative

Usage:
    from rpg.core.orchestrator import run_turn
    result = run_turn(session, player_input)

This replaces the old scattered loop logic with a single authoritative
turn execution that ensures all systems cooperate in the right order.
"""

from typing import Any, Dict, List, Optional

from rpg.ai.director_bridge import apply_director_to_npcs, clear_director_goals
from rpg.memory import EPISODE_BUILD_THRESHOLD
from rpg.memory.episodic import Episode
from rpg.memory.memory_manager import MemoryManager


def _get_or_create_memory_manager(session) -> MemoryManager:
    """Get existing MemoryManager from session or create and attach one."""
    if not hasattr(session, 'memory_manager') or session.memory_manager is None:
        session.memory_manager = MemoryManager(session=session)
    return session.memory_manager


def _trigger_episode_build(session, memory_manager: MemoryManager) -> Optional[Episode]:
    """Check if episode should be built from session recent_events.
    
    When session.recent_events reaches the threshold, force-build
    an episode and clear the buffer.
    """
    recent = getattr(session, 'recent_events', [])
    if len(recent) >= EPISODE_BUILD_THRESHOLD:
        episode = memory_manager.force_build_episode(list(recent))
        recent.clear()
        return episode
    return None


def _consolidate_periodic(
    session,
    memory_manager: MemoryManager,
    interval: int = 10,
) -> None:
    """Run memory consolidation at regular intervals.
    
    Consolidation is expensive, so it's not done every turn.
    This checks if enough turns have passed and triggers it.
    
    Args:
        session: The current game session.
        memory_manager: The MemoryManager to consolidate.
        interval: Number of turns between consolidations.
    """
    world_time = getattr(session.world, 'time', 0)
    if world_time % interval == 0 and world_time > 0:
        memory_manager.consolidate(current_tick=world_time)


def _enrich_npcs_with_memory(session) -> None:
    """Step 5: Enrich NPCs with memory-derived context.
    
    PATCH 5: Memory must drive behavior.
    This retrieves recent memories for each NPC and updates their
    emotional state and relationships before planning.
    
    Args:
        session: The current game session.
    """
    npcs = session.npcs.values() if hasattr(session.npcs, 'values') else session.npcs
    
    for npc in npcs:
        if not getattr(npc, 'is_active', True):
            continue
            
        _enrich_npc_with_memory(npc, session)


def _enrich_npc_with_memory(npc, session) -> None:
    """Enrich a single NPC with memories.
    
    Uses MemoryManager if available, otherwise falls back to old system.
    
    Args:
        npc: The NPC to enrich.
        session: The current game session.
    """
    # Try new MemoryManager first
    memory_manager = getattr(session, 'memory_manager', None)
    if memory_manager:
        query_entities = [npc.id, "player"]
        
        memories = memory_manager.retrieve(
            query_entities=query_entities,
            limit=5,
            mode="general",
        )
        
        formatted = memory_manager.get_context_for(
            query_entities=query_entities,
            max_items=5,
            format_type="narrative",
        )
        
        if memories:
            npc.emotional_state["recent_memories"] = [
                item.summary if hasattr(item, 'summary') else str(item)
                for _, item in memories[:3]
            ]
            npc.emotional_state["memory_context"] = formatted
        return
    
    # Fallback to old memory system
    if hasattr(session, 'memory_system'):
        memories = session.memory_system.retrieve(npc.id)
    elif hasattr(npc, 'memory') and isinstance(npc.memory, dict):
        memories = npc.memory.get("events", [])
    else:
        memories = []
        
    # Update emotional state from memories
    if memories:
        npc.emotional_state["recent_memories"] = memories[-5:]
        
    # Update relationships from memories
    cond1 = hasattr(session, "memory_system")
    cond2 = hasattr(session.memory_system, "get_relationships")
    if cond1 and cond2:
        relationships = session.memory_system.get_relationships(npc.id)
        npc.emotional_state["relationships"] = relationships


def run_turn(session, player_input: str) -> Dict[str, Any]:
    """Execute one complete turn of the RPG simulation.
    
    This is the authoritative turn loop from the design specification.
    It ensures all systems are called in the correct dependency order.
    
    Turn Order:
    1. Interpret player intent (Brain)
    2. Story Director decides narrative direction
    3. Apply world state updates from Director
    4. Apply NPC goal updates from Director
    5. Enrich NPCs with memory (memory drives behavior)
    6. NPCs plan their actions (GOAP)
    7. Convert actions to events
    8. Inject story events from Director
    9. Check if scene update is needed
    10. Process all events (system reactions)
    11. Update memory with events (4-layer system)
    12. Generate narrative output
    13. Clear per-turn state
    
    Args:
        session: The current game session.
        player_input: The player's input text for this turn.
        
    Returns:
        Dict with turn result including narration, events, and state.
    """
    # 1. Interpret player intent
    intent = _interpret_player(session, player_input)
    
    # 2. Story Director decides story direction
    director_output = session.story_director.decide(session, intent)
    
    # Apply tension delta from Director
    session.tension = getattr(session, 'tension', 0.0) + director_output.tension_delta
    
    # 3. Apply world state updates from Director
    _apply_world_updates(session, director_output)
    
    # 4. Apply NPC goal updates from Director
    apply_director_to_npcs(session, director_output)
    
    # 5. Enrich NPCs with memory (PATCH 5)
    _enrich_npcs_with_memory(session)
    
    # 6. NPCs plan their actions (GOAP)
    npc_actions = _plan_npc_actions(session)
    
    # 7. Convert actions to events
    events = _convert_actions_to_events(session, npc_actions)
    
    # 8. Inject story events from Director (CRITICAL)
    events.extend(director_output.story_events)
    
    # 9. Check if scene update is needed (PATCH 7)
    if _should_update_scene(events):
        _update_scene(session, events)
    
    # 10. Process all events (event bus dispatch)
    session.event_bus.process(session)
    
    # 11. Update memory with events (4-layer system)
    _update_memory(session, events)
    
    # 11b. Feed events through MemoryManager pipeline
    memory_manager = _get_or_create_memory_manager(session)
    memory_manager.add_events(events, current_tick=getattr(session.world, 'time', 0))
    
    # 11c. Check for episode building from session recent_events
    _trigger_episode_build(session, memory_manager)
    
    # 11d. Periodic consolidation
    _consolidate_periodic(session, memory_manager)
    
    # 12. Generate narrative output
    narration = _generate_narration(session, events)
    
    # 13. Clear per-turn state
    _clear_per_turn_state(session)
    
    return {
        "narration": narration,
        "events": events,
        "tension": session.tension,
        "director_output": director_output.to_dict(),
    }


def _interpret_player(session, player_input: str) -> Dict[str, Any]:
    """Step 1: Interpret player input into structured intent.
    
    Uses the unified brain to classify the player's action into
    a structured format that other systems can consume.
    
    Args:
        session: The current game session.
        player_input: The player's input text.
        
    Returns:
        Dict with structured intent (type, intent, target, tone).
    """
    if hasattr(session, 'brain') and session.brain:
        return session.brain.interpret(player_input)
    
    # Fallback: simple classification
    return {
        "type": "action",
        "intent": player_input,
        "target": None,
        "tone": "neutral",
    }


def _apply_world_updates(session, director_output) -> None:
    """Step 3: Apply world state updates from the Director.
    
    Updates global world state based on Director decisions.
    This might change things like alert levels, weather, time of day, etc.
    
    Args:
        session: The current game session.
        director_output: The Director's output with world updates.
    """
    if not director_output.has_world_updates():
        return
        
    world = getattr(session, 'world', None)
    if world is None:
        return
        
    for key, value in director_output.world_state_updates.items():
        if hasattr(world, key):
            setattr(world, key, value)
        elif hasattr(world, 'update'):
            world.update({key: value})


def _plan_npc_actions(session) -> List[Dict[str, Any]]:
    """Step 6: NPCs plan their actions using GOAP.
    
    Each active NPC plans their next action(s) based on their
    current goals (which may include Director-injected goals).
    
    Args:
        session: The current game session.
        
    Returns:
        List of action dicts from all NPCs.
    """
    from rpg.ai.npc_planner import decide as npc_decide
    
    npc_actions = []
    npcs = session.npcs.values() if hasattr(session.npcs, 'values') else session.npcs
    
    for npc in npcs:
        if not getattr(npc, 'is_active', True):
            continue
            
        try:
            action = npc_decide(npc, session)
            action["npc_id"] = npc.id
            npc_actions.append(action)
        except Exception:
            # Don't let one NPC's error break the whole turn
            continue
            
    return npc_actions


def _convert_actions_to_events(
    session, npc_actions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Step 7: Convert NPC actions to events.
    
    Translates high-level actions like "attack" or "move" into
    concrete events that other systems can react to.
    
    Args:
        session: The current game session.
        npc_actions: List of action dicts from NPCs.
        
    Returns:
        List of event dicts.
    """
    from rpg.game_loop.main import handle_action
    
    events = []
    for action in npc_actions:
        # Execute the action (which may publish events)
        handle_action(session, action)
        events.append({
            "type": "npc_action",
            "npc_id": action.get("npc_id"),
            "action": action.get("action"),
        })
        
    return events


def _should_update_scene(events: List[Dict[str, Any]]) -> bool:
    """Step 9: Check if scene regeneration is needed.
    
    PATCH 7: Scene update triggers.
    Scene should update when significant events occur.
    
    Args:
        events: List of events from this turn.
        
    Returns:
        True if scene should be regenerated.
    """
    trigger_types = {"damage", "death", "story_event", "critical_hit"}
    
    for event in events:
        if event.get("type") in trigger_types:
            return True
            
    return False


def _update_scene(session, events: List[Dict[str, Any]]) -> None:
    """Step 9: Regenerate the scene if needed.
    
    Uses the scene generator to create a new scene representation
    based on current state and events.
    
    Args:
        session: The current game session.
        events: Events that occurred this turn.
    """
    if hasattr(session, 'scene_generator'):
        session.scene = session.scene_generator.generate(session)


def _update_memory(session, events: List[Dict[str, Any]]) -> None:
    """Step 11: Update NPC memories with new events.
    
    Stores the turn's events so NPCs can remember them for
    future decision-making.
    
    Args:
        session: The current game session.
        events: Events that occurred this turn.
    """
    if hasattr(session, 'memory_system'):
        session.memory_system.update(events)


def _generate_narration(
    session, events: List[Dict[str, Any]]
) -> Optional[str]:
    """Step 12: Generate narrative output.
    
    Converts the mechanical events into narrative text for the player.
    
    Args:
        session: The current game session.
        events: Events that occurred this turn.
        
    Returns:
        Narration text, or None if not available.
    """
    if hasattr(session, 'narrator'):
        return session.narrator.generate(session)
    return None


def _clear_per_turn_state(session) -> None:
    """Step 13: Clear state that should not persist between turns.
    
    This prevents accumulation of per-turn directives like
    Director-injected goals.
    
    Args:
        session: The current game session.
    """
    clear_director_goals(session)