from rpg.models.npc import NPC
from rpg.models.game_state import GameState
from rpg.npc.goals import Goal
from rpg.scene.scene import add_character
from rpg.game_loop.main import game_loop

# Create NPCs
npc1 = NPC("1", "Warrior", "Brave warrior", "heroes", hp=50)
npc1.goals = [Goal("attack", 5), Goal("survive", 1)]

npc2 = NPC("2", "Orc", "Fierce orc", "monsters", hp=60)
npc2.goals = [Goal("attack", 5), Goal("survive", 1)]

# Create game state
state = GameState()
add_character(state.scene, npc1)
add_character(state.scene, npc2)

# Run multiple turns
results = game_loop(state, max_turns=5)

# Print results
print("NPC1 HP:", npc1.hp)
print("NPC1 Memory:", npc1.memory)
print("NPC2 HP:", npc2.hp)
print("NPC2 Memory:", npc2.memory)

print("\n--- GAME LOG ---")

for turn in results:
    print(f"\nTurn {turn['turn']}:")
    for action in turn["actions"]:
        print(action["description"])