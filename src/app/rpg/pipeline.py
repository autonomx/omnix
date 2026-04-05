from .brain.unified_brain import unified_brain
from .memory import update_memory
from .models import NPC, GameSession
from .narrative_context import build_context, update_tension
from .pipeline_adapter import adapt_pipeline_result
from .scene_generator import generate_scene
from .simulation import apply_events, process

# In-memory game store for save/load
_game_store = {}


def create_new_game(seed=None, genre="fantasy", player_name="Player", character_class="", custom_lore=None, custom_rules=None, custom_story=None, world_prompt=None):
    session = GameSession()
    session.player.id = player_name
    session.npcs = [NPC("guard", "Guard")]
    return session


def save_game(session, game_id="default"):
    """Save a game session to the in-memory store."""
    _game_store[game_id] = session
    return {"ok": True, "game_id": game_id}


def load_game(game_id="default"):
    """Load a game session from the in-memory store."""
    return _game_store.get(game_id)


def list_games():
    """List all saved game IDs."""
    return list(_game_store.keys())


def delete_game(game_id="default"):
    """Delete a saved game."""
    if game_id in _game_store:
        del _game_store[game_id]
        return {"ok": True}
    return {"ok": False, "error": "Game not found"}

# ---------------------------------------------------------------------------
# Game creation pipeline helpers (used by routes.py streaming creation)
# ---------------------------------------------------------------------------

def build_game_context(data: dict) -> dict:
    """Build a context dict for the streaming game-creation pipeline."""
    return {
        "seed": data.get("seed"),
        "genre": data.get("genre", "medieval fantasy"),
        "player_name": data.get("player_name", "Player"),
        "character_class": data.get("character_class", ""),
        "custom_lore": data.get("lore") or data.get("custom_lore"),
        "custom_rules": data.get("rules") or data.get("custom_rules"),
        "custom_story": data.get("story") or data.get("custom_story"),
        "world_prompt": data.get("world_prompt"),
        "stage_results": {},
    }


def stage_world(ctx: dict) -> dict:
    """Generate world data and store it in the context."""
    ctx["world_data"] = {
        "name": f"World of {ctx.get('genre', 'Fantasy')}",
        "genre": ctx.get("genre", "medieval fantasy"),
        "description": f"A {ctx['genre']} world awaits your adventure.",
        "lore": "",
    }
    ctx["stage_results"]["world"] = ctx["world_data"]
    return ctx


def stage_environment(ctx: dict) -> dict:
    """Generate environment details."""
    ctx.setdefault("world_data", {})
    ctx["environment_data"] = {"locations": [], "description": "A vast landscape."}
    ctx["stage_results"]["environment"] = ctx["environment_data"]
    return ctx


def stage_factions(ctx: dict) -> dict:
    """Generate factions."""
    ctx.setdefault("world_data", {})
    ctx["faction_data"] = {"factions": []}
    ctx["stage_results"]["factions"] = ctx["faction_data"]
    return ctx


def stage_npcs(ctx: dict) -> dict:
    """Generate NPCs."""
    ctx.setdefault("world_data", {})
    ctx["npc_data"] = {"npcs": []}
    ctx["stage_results"]["npcs"] = ctx["npc_data"]
    return ctx


def stage_story(ctx: dict) -> dict:
    """Generate initial story/quest hooks."""
    ctx.setdefault("world_data", {})
    ctx["story_data"] = {"hooks": [], "quests": []}
    ctx["stage_results"]["story"] = ctx["story_data"]
    return ctx


def finalize_game(ctx: dict):
    """Turn the assembled context into a GameSession and save it."""
    session = GameSession()
    session.player.id = ctx.get("player_name", "Player")
    world = ctx.get("world_data", {})
    session.world.name = world.get("name", "")
    session.world.genre = world.get("genre", "")
    session.world.description = world.get("description", "")
    session.world.lore = world.get("lore", "")
    session.npcs = [NPC("guard", "Guard")]
    save_game(session, session.session_id)
    return session


def replay_turn(turn_log, session):
    """Re-execute a turn from its stored TurnLog (deterministic replay)."""
    player_input = turn_log.input if hasattr(turn_log, "input") else ""
    return execute_turn(session, player_input)


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