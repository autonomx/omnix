from rpg.models.game_state import GameState
from rpg.npc.brain import npc_decide
from rpg.actions.resolution import resolve_action
from rpg.memory.memory import remember_event

def get_player_input():
    # Stub: return a basic action
    return {"type": "wait", "stat": "none"}

def apply_player_action(state: GameState, player_action):
    # Stub: apply player action to state
    pass

def apply_outcome(state: GameState, npc, action, outcome):
    # Stub: apply outcome to state and npc
    if outcome == "failure" and action.type == "attack":
        npc.hp -= 10  # Example damage

def update_scene(scene):
    # Stub: update scene summary or something
    scene.summary = f"Scene with {len(scene.characters)} characters."

def game_loop(state: GameState):
    while state.active:
        player_action = get_player_input()
        apply_player_action(state, player_action)

        for npc in state.scene.characters:
            action = npc_decide(npc, state.scene)
            outcome = resolve_action(npc, action, difficulty=10)
            apply_outcome(state, npc, action, outcome)
            remember_event(npc, {"action": action.type, "outcome": outcome})

        update_scene(state.scene)

        # For demo, stop after one loop
        state.active = False