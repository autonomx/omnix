from .simulation import process, apply_events
from .pipeline_adapter import adapt_pipeline_result
from .brain.unified_brain import unified_brain
from .narrative_context import build_context, update_tension
from .scene_generator import generate_scene
from .memory import update_memory
from .models import GameSession, NPC

def create_new_game(seed=None, genre="fantasy", player_name="Player", character_class="", custom_lore=None, custom_rules=None, custom_story=None, world_prompt=None):
    session = GameSession()
    session.player.id = player_name
    session.npcs = [NPC("guard", "Guard")]
    return session

def execute_turn(session, player_input):
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
    npc_events = []
    for action in npc_actions:
        npc_intent = {
            "action": action["action"],
            "target": "player",
            "source": action["npc_id"]
        }
        npc_raw = process(session, npc_intent)
        npc_result = adapt_pipeline_result(npc_raw)
        npc_events.extend(npc_result["events"])

    # 3. Apply events
    all_events = result["events"] + npc_events
    apply_events(session, all_events)

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