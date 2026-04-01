import random

from rpg.ai.npc_planner import choose_target
from rpg.spatial import distance
from rpg.brain.unified_brain import unified_brain
from rpg.memory import update_memory
from rpg.narrative_context import build_context, update_tension
from rpg.pipeline_adapter import adapt_pipeline_result
from rpg.scene_generator import generate_scene
from rpg.simulation import find_npc, process
from rpg.systems import combat_system


def process_npc_actions(session, npc_actions):
    events = []

    for action in npc_actions:
        npc = next((n for n in session.npcs if n.id == action["npc_id"]), None)
        if not npc:
            continue

        if action["action"] == "attack":
            target = choose_target(npc, session)
            # Only attack if in range (spatial constraint)
            attack_target = find_npc(session, target)
            if attack_target and attack_target.is_active and distance(npc.position, attack_target.position) <= 1:
                events.append({
                    "type": "damage",
                    "source": action["npc_id"],
                    "target": target,
                    "amount": 5
                })
        elif action["action"] == "move_toward":
            from rpg.ai.npc_planner import move_toward
            move_toward(npc, session)
        elif action["action"] == "wander":
            _npc_wander(npc, session)
        elif action["action"] == "observe":
            pass  # Observe: no state change, just perception

    return events


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


def execute_turn(session, player_input):
    if not hasattr(session, "_systems_initialized"):
        session.event_bus.session = session
        combat_system.register(session.event_bus, session)
        session._systems_initialized = True

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

    # 2.5 Simulation (NPC actions)
    npc_events = process_npc_actions(session, npc_actions)

    # 3. Apply events
    all_events = result["events"] + npc_events
    for event in all_events:
        session.event_bus.emit(event)

    # 4. Memory update
    session.recent_events.extend(all_events)
    session.recent_events = session.recent_events[-100:]

    update_memory(session, all_events)

    # 5. Advance world time
    session.world.time += 1

    # 7. Scene
    scene = generate_scene(
        session=session,
        director=director,
        result=result,
        event=event,
        npc_actions=npc_actions
    )

    # 8. Update tension
    session.narrative_state["tension"] = update_tension(
        session.narrative_state["tension"],
        director["tension"]
    )

    return scene
