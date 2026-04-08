"""Game Loop - Event-driven simulation core.

The game loop follows this pattern:
1. NPC decisions (AI planning)
2. Convert decisions -> events (publish to event bus)
3. Process ALL events (systems react independently)
4. Advance time
"""

import random

from rpg.ai.npc_planner import choose_target, decide
from rpg.brain.unified_brain import unified_brain
from rpg.emotion import decay_emotions
from rpg.narrative_context import build_context, update_tension
from rpg.pipeline_adapter import adapt_pipeline_result
from rpg.scene.grounding import build_grounding_block
from rpg.scene.validator import validate_scene
from rpg.scene_generator import generate_scene
from rpg.simulation import find_npc, process
from rpg.spatial import distance
from rpg.story.director import StoryDirector

# Import system registration
from rpg.systems import (
    combat_system,
    debug_system,
    emotion_system,
    memory_system,
    scene_system,
)


def handle_action(session, action):
    """Convert an NPC action into events published to the event bus.
    
    This function translates high-level actions into events.
    All state changes happen through the event system.
    """
    bus = session.event_bus
    npc_id = action.get("npc_id")
    
    if action["action"] == "attack":
        npc = next((n for n in session.npcs if n.id == npc_id), None)
        if not npc:
            return
        
        target_id = choose_target(npc, session)
        target = find_npc(session, target_id)
        
        # Only attack if in range (spatial constraint)
        if target and target.is_active and distance(npc.position, target.position) <= 2:
            bus.publish({
                "type": "damage",
                "source": npc_id,
                "target": target_id,
                "amount": 5,
                "tick": session.world.time
            })
    
    elif action["action"] == "move_toward":
        npc = next((n for n in session.npcs if n.id == npc_id), None)
        if npc:
            _move_toward_npc(npc, session)
    
    elif action["action"] == "wander":
        npc = next((n for n in session.npcs if n.id == npc_id), None)
        if npc:
            _npc_wander(npc, session)
    
    elif action["action"] == "observe":
        # Observe: no state change, just perception
        # Record observation in memory via event
        pass


def _move_toward_npc(npc, session):
    """Move NPC toward target using A* pathfinding."""
    from rpg.spatial import astar
    
    target_id = npc.emotional_state.get("top_threat")
    target = find_npc(session, target_id)
    
    if not target:
        return
    
    path = astar(npc.position, target.position, session)
    
    if len(path) > 1:
        npc.position = path[1]


def _npc_wander(npc, session):
    """Random wandering behavior for idle NPCs."""
    x, y = npc.position
    max_x, max_y = session.world.size
    
    options = [
        (x + dx, y + dy)
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if 0 <= x + dx < max_x and 0 <= y + dy < max_y
    ]
    
    if options:
        npc.position = random.choice(options)


def init_systems(session, enable_debug=False):
    """Register all systems with the event bus.
    
    This function sets up the event-driven architecture by
    subscribing each system to the relevant event types.
    
    Args:
        session: The current game session.
        enable_debug: If True, enables the debug system for logging all events.
    """
    # Guard against duplicate system registration using getattr pattern
    # This is more robust than hasattr as it handles session reuse/reset
    if getattr(session, "_systems_initialized", False):
        return

    bus = session.event_bus
    
    # Combat system handles damage and death (priority -10)
    combat_system.register(bus, session)
    
    # Emotion system reacts to damage and death (priority 0)
    emotion_system.register(bus, session)
    
    # Scene system records all events for narrative (priority 5)
    scene_system.register(bus, session)
    
    # Memory system tracks all events (priority 10)
    memory_system.register(bus, session)
    
    # Debug system logs all events (priority 20) - optional
    if enable_debug:
        debug_system.register(bus, session)
    
    session._systems_initialized = True


def init_story_director(session):
    """Initialize the Story Director for this game session.
    
    Args:
        session: The current game session.
    """
    session.story_director = StoryDirector()


def game_tick(session):
    """Execute one game tick using event-driven architecture.
    
    1. NPC decisions (AI planning)
    2. Convert actions -> events
    3. Process ALL events (systems react independently)
    4. Update Story Director with events
    5. Advance time
    """
    # Mark systems as initialized if needed
    if not hasattr(session, "_systems_initialized"):
        init_systems(session)
    
    # Initialize story director if not present
    if not hasattr(session, 'story_director'):
        init_story_director(session)
    
    # 1. NPC decisions
    for npc in session.npcs:
        if not npc.is_active:
            continue
        
        # Decay emotions before decision
        decay_emotions(npc, session.world.time)
        
        # 🔥 Periodic belief decay (every 10 ticks)
        if session.world.time % 10 == 0 and hasattr(npc, 'belief_system'):
            npc.belief_system.decay(dt=1.0)
        
        # Decide action
        action = decide(npc, session)
        action["npc_id"] = npc.id
        
        # 2. Convert actions -> events
        handle_action(session, action)

    # 3. Process ALL events (tick-bound batch processing)
    session.event_bus.process(session)
    
    # 4. 🔥 Update Story Director with processed events
    collected_events = getattr(session, '_scene_events', [])
    session.story_director.update(session, collected_events)

    # 5. Advance time
    session.world.time += 1


def execute_turn(session, player_input):
    """Execute a complete turn with player input and NPC simulation.
    
    This function wraps the core game_tick with scene generation,
    narrative context updates, and story director integration.
    """
    # Initialize systems if needed
    if not hasattr(session, "_systems_initialized"):
        session.event_bus.session = session
        init_systems(session)
    
    # Initialize story director if not present
    if not hasattr(session, 'story_director'):
        init_story_director(session)

    # Build narrative context
    context = build_context(session)

    # 1. Unified brain
    brain_output = unified_brain(session, player_input, context)
    
    intent = brain_output["intent"]
    director = brain_output["director"]
    event = brain_output["event"]
    npc_actions = brain_output["npc_actions"]

    # 2. Simulation (player)
    raw_result = process(session, intent)
    result = adapt_pipeline_result(raw_result)

    # 2.5 Simulation (NPC actions) - use shared handle_action for consistency
    for action in npc_actions:
        npc = next((n for n in session.npcs if n.id == action.get("npc_id")), None)
        if not npc:
            continue
        
        # Use shared handle_action to prevent logic drift
        handle_action(session, action)

    # 3. Process ALL events (tick-bound batch processing)
    session.event_bus.process(session)

    # 4. 🔥 Update Story Director with processed events
    collected_events = getattr(session, '_scene_events', [])
    session.story_director.update(session, collected_events)

    # 5. Advance world time
    session.world.time += 1

    # 6. Build grounding block for scene validation
    grounding = build_grounding_block(session, result.get("events", []), npc_actions)

    scene = generate_scene(
        session=session,
        director=director,
        result=result,
        event=event,
        npc_actions=npc_actions
    )

    # 8. Additional validation at game loop level
    if scene and scene.narration:
        if not validate_scene(scene.narration, grounding):
            scene.narration = "[ERROR: Scene rejected due to hallucination]"

    # 9. Update tension (combine old system with story director)
    director_tension = session.story_director.global_tension
    session.narrative_state["tension"] = update_tension(
        session.narrative_state["tension"],
        director_tension
    )

    return scene


def process_npc_actions(session, npc_actions):
    """Convert NPC actions to events (legacy compatibility).
    
    This function maintains compatibility with existing code that
    calls process_npc_actions directly.
    """
    events = []
    bus = session.event_bus

    for action in npc_actions:
        npc = next((n for n in session.npcs if n.id == action.get("npc_id")), None)
        if not npc:
            continue

        if action["action"] == "attack":
            target = choose_target(npc, session)
            attack_target = find_npc(session, target)
            if attack_target and attack_target.is_active and distance(npc.position, attack_target.position) <= 1:
                event = {
                    "type": "damage",
                    "source": action.get("npc_id"),
                    "target": target,
                    "amount": 5,
                    "tick": session.world.time
                }
                bus.publish(event)
                events.append(event)
        elif action["action"] == "move_toward":
            _move_toward_npc(npc, session)
        elif action["action"] == "wander":
            _npc_wander(npc, session)
        elif action["action"] == "observe":
            pass

    return events