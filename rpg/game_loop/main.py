from rpg.models.game_state import GameState
from rpg.npc.brain import npc_decide
from rpg.actions.resolution import resolve_action
from rpg.memory.memory import remember_event
from rpg.scene.scene import remove_dead
from rpg.narration.generator import generate_narration
from rpg.models.action_result import ActionResult

def get_player_input():
    # Stub: return a basic action
    return {"type": "wait", "stat": "none"}

def apply_player_action(state: GameState, player_action):
    # Stub: apply player action to state
    pass

def apply_outcome(state: GameState, npc, action, outcome):
    # Apply combat outcomes properly
    if action.type == "attack" and action.target:
        if outcome in ["success", "critical_success"]:
            action.target.hp -= 10
        elif outcome == "failure":
            npc.hp -= 2  # recoil penalty (optional)

def update_scene(scene):
    # Build meaningful scene summary
    summary_parts = []
    for c in scene.characters:
        summary_parts.append(f"{c.name}(HP:{c.hp}, faction:{c.faction})")
    scene.summary = " | ".join(summary_parts)

def game_tick(state: GameState):
    player_action = get_player_input()
    apply_player_action(state, player_action)

    results = []

    for npc in list(state.scene.characters):
        action = npc_decide(npc, state.scene)
        outcome = resolve_action(npc, action, difficulty=get_action_difficulty(action))

        apply_outcome(state, npc, action, outcome)

        memory = npc.memory["events"][-5:]

        narration = generate_narration(
            npc,
            action,
            outcome,
            state.scene,
            memory
        )

        result = ActionResult(
            actor_id=npc.id,
            action_type=action.type,
            outcome=outcome,
            description=narration["description"],
            dialogue=narration["dialogue"],
            emotion=narration["emotion"]
        )

        # Update emotional state with decay
        npc.update_emotions(narration["emotion"])

        # Emotion affects relationships
        if narration["emotion"] == "angry" and action.target:
            npc.opinions[action.target.name] = npc.opinions.get(action.target.name, 0) - 1

        results.append(result.to_dict())

        remember_event(npc, {
            "actor": npc.id,
            "action": action.type,
            "target": action.target.id if action.target else None,
            "outcome": outcome,
            "description": narration["description"],
            "emotion": narration["emotion"]
        })

    remove_dead(state.scene)
    update_scene(state.scene)

    return results


def get_action_difficulty(action):
    if action.type == "attack":
        return 10
    if action.type == "flee":
        return 8
    return 10


def game_loop(state: GameState, max_turns: int = 10):
    turn = 0
    turn_results = []

    while state.active and turn < max_turns:
        results = game_tick(state)
        turn_results.append({
            "turn": turn,
            "actions": results
        })
        turn += 1

    return turn_results